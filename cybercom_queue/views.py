# Create your views here.
from rest_framework.settings import api_settings
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.permissions import IsAuthenticatedOrReadOnly,DjangoModelPermissionsOrAnonReadOnly,AllowAny
from rest_framework.views import APIView
from cybercom_queue.ccelery.q import QueueTask, list_tasks, task_docstring
from cybercom_queue.models import Run_model
from rest_framework.renderers import JSONRenderer, JSONPRenderer
from renderer import QueueRunBrowsableAPIRenderer
from rest_framework.parsers import JSONParser,MultiPartParser,FormParser,FileUploadParser
from cybercom_queue.util import trim
from rest_framework.authtoken.models import Token
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
#task = list_tasks()['available_tasks']
#from rest_framework.viewsets import ModelViewSet
#from serializer import FileUploadSerializer
import os

q = QueueTask()


class Queue(APIView):
    permission_classes = ( IsAuthenticatedOrReadOnly,)

    def __init__(self,q=q, *args, **kwargs):
        self.q = q #QueueTask()
        self.task = self.q.list()['available_tasks']
        self.task_list = None
        super(Queue, self).__init__(*args, **kwargs)

    def get(self, request,format=None):
        if not self.task_list:
            self.task_list = []
            for task in self.task:
                self.task_list.append(reverse('run-main',kwargs={'task_name':task},request=request))
                #self.task_list.append(reverse('%s-run' % task, request=request))
        return Response({
            'Tasks': self.task_list,
            'Task History': reverse('queue-user-tasks',request=request)
        })


class Run(APIView):
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly,)
    model = Run_model
    parser_classes = (JSONParser,MultiPartParser,FormParser)
    renderer_classes = (QueueRunBrowsableAPIRenderer, JSONRenderer, JSONPRenderer,)

    def __init__(self,q=q, *args, **kwargs):
        self.q = q #QueueTask()
        self.tasks_queues = self.q.list()
        # self.task = self.q.list()['available_tasks']
        # self.task_list = None
        super(Run, self).__init__(*args, **kwargs)

    def get_username(self, request):
        username = "guest"
        if request.user.is_authenticated():
            username = request.user.username
        return username

    def get(self, request,task_name=None,format=None):
        #task_name = filter(None, request._request.path.split('/'))[-1]
        docstring = trim(task_docstring(task_name))
        curl_url = reverse('run-main',kwargs={'task_name':task_name},request=request)
        #reverse("%s-run" % (task_name), request=request)
        username= self.get_username(request)
        if not username == "guest":
            token = Token.objects.get_or_create(user=self.request.user)
            auth_token = str(token[0])
        else:
            auth_token = "< authorized-token > "
        data = {'task_name': task_name, 'task_docstring': docstring, 'task_url': curl_url, 'queue': 'celery','auth_token':auth_token}
        return Response(data)

    def post(self, request,task_name=None,format=None):
        if not task_name:
            task_name = request.DATA.get('function', None)
        if task_name not in self.tasks_queues['available_tasks']:
            raise Exception("%s Task is not available" % (task_name))
        queue = request.DATA.get('queue', 'celery')
        if queue not in self.tasks_queues['available_queues']:
            raise Exception("%s Queue is not available" % (queue))
        args = request.DATA.get('args', [])
        kwargs = request.DATA.get('kwargs', {})
        tags = request.DATA.get('tags',[])
        result = self.q.run(task_name, args, kwargs, queue, self.get_username(request),tags)
        result['result_url']=reverse('queue-task-result', kwargs={'task_id':result['task_id']}, request=request)
        return Response(result)

class UserResult(APIView):
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly,)
    model = Run_model
    parser_classes = (JSONParser,)

    def __init__(self,q=q, *args, **kwargs):
        self.q = q #QueueTask()
        super(UserResult, self).__init__(*args, **kwargs)

    def get(self, request, task_id=None,format=None):
        if task_id:
            try:
                data = self.q.task(task_id)
            except Exception as inst:
                data = {'task_id': task_id, 'error': inst.message}
            return Response(data)


class UserTasks(APIView):
    permission_classes = (DjangoModelPermissionsOrAnonReadOnly,)
    model = Run_model

    def __init__(self,q=q, *args, **kwargs):
        self.q = q #QueueTask()
        self.task = self.q.list()['available_tasks']
        self.task_list = None
        # self.mongo_encoder = MongoEncoder()
        super(UserTasks, self).__init__(*args, **kwargs)

    def get_username(self, request):
        username = "guest"
        if request.user.is_authenticated():
            username = request.user.username
        return username

    def get(self, request,format=None, **kwargs):
        result = {'count': 0, 'next': None, 'previous': None, 'results': []}
        page_parm = api_settings.user_settings.get('PAGINATE_BY_PARAM', 'page_size')
        if page_parm in request.GET:
            limit = request.GET.get(page_parm, 10)
        else:
            limit = api_settings.user_settings.get('PAGINATE_BY', 10)
        # Set page to 1 or page GET
        page = request.GET.get('page', 1)
        try:
            page = int(page)
        except:
            page = 1
        task_name = request.GET.get('taskname', None)
        username = self.get_username(request)
        data = self.q.history(username, task_name=task_name, page=page, limit=limit,request=request)
        return Response(data) 

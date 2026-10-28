from django.contrib.auth import logout
from django.http import JsonResponse


class AuthorizationVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.path not in {
            '/api/v1/auth/login',
            '/api/v1/health',
        }:
            profile = getattr(request.user, 'profile', None)
            version = getattr(profile, 'session_version', 0)
            if request.session.get('_auth_epoch', 0) != version:
                logout(request)
                response = JsonResponse(
                    {
                        'error': {
                            'code': 'UNAUTHORIZED',
                            'message': '授权已变更，请重新登录',
                            'details': {},
                            'request_id': getattr(request, 'request_id', ''),
                        }
                    },
                    status=401,
                )
                response['Cache-Control'] = 'no-store'
                return response
        return self.get_response(request)

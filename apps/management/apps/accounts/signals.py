from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def bind_authorization_version(sender, request, user, **kwargs):
    if request is not None:
        request.session['_auth_epoch'] = getattr(
            getattr(user, 'profile', None), 'session_version', 0
        )

from rest_framework.throttling import BaseThrottle
from apps.accounts.utils import get_client_ip, _check_rate_limit


class SignupEmailThrottle(BaseThrottle):
    def allow_request(self, request, view):
        email = (request.data.get("email") or "").lower().strip()
        if not email:
            return True
        allowed, _ = _check_rate_limit(f"rl:signup:email:{email}", 10)
        return allowed
    def wait(self): return 3600


class SignupIPThrottle(BaseThrottle):
    def allow_request(self, request, view):
        allowed, _ = _check_rate_limit(f"rl:signup:ip:{get_client_ip(request)}", 20)
        return allowed
    def wait(self): return 3600


class LoginEmailThrottle(BaseThrottle):
    def allow_request(self, request, view):
        email = (request.data.get("email") or "").lower().strip()
        if not email:
            return True
        allowed, _ = _check_rate_limit(f"rl:login:email:{email}", 15)
        return allowed
    def wait(self): return 3600


class LoginIPThrottle(BaseThrottle):
    def allow_request(self, request, view):
        allowed, _ = _check_rate_limit(f"rl:login:ip:{get_client_ip(request)}", 20)
        return allowed
    def wait(self): return 3600


class VerifyIPThrottle(BaseThrottle):
    def allow_request(self, request, view):
        allowed, _ = _check_rate_limit(f"rl:verify:ip:{get_client_ip(request)}", 20)
        return allowed
    def wait(self): return 3600

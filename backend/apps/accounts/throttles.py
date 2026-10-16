from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthRateThrottle(AnonRateThrottle):
    scope = "auth"


class OTPRateThrottle(AnonRateThrottle):
    scope = "otp"


class PinLoginRateThrottle(AnonRateThrottle):
    scope = "pin_login"


class PINRateThrottle(UserRateThrottle):
    scope = "pin"

import os
from enum import Enum


class ServiceType(Enum):
    UBERDOG = "UberDOG"
    AI      = "AI/District"
    CLIENT  = "Client"


class ErrorTrackingService:

    def __init__(self, service: ServiceType, version: str):

        self.service_type: ServiceType = service
        self.version = version  # The version of the game

    def want_error_reporting(self) -> bool:
        return os.environ.get('WANT_ERROR_REPORTING', '').lower() in ('1', 'true', 't', 'yes', 'on')

    def report(self, exception: Exception):
        raise NotImplementedError


class BasicErrorTrackingService(ErrorTrackingService):

    def want_error_reporting(self) -> bool:
        return False

    def report(self, exception: Exception):
        pass

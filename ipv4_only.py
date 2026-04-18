import socket


_old_getaddrinfo = socket.getaddrinfo


def _ipv4_getaddrinfo(*args, **kwargs):
    responses = _old_getaddrinfo(*args, **kwargs)
    return [
        response for response in responses if response[0] == socket.AF_INET
    ]


socket.getaddrinfo = _ipv4_getaddrinfo

"""Exercise the real HTTP parser/handler without binding or starting a server."""
import io
import json
from types import SimpleNamespace
from server import UhiDashboardHandler

SESSION = 'unit-test-session-capability'

class Socket:
    def __init__(self, request): self.input=io.BytesIO(request); self.output=io.BytesIO()
    def makefile(self, mode, *args): return self.input
    def sendall(self, data): self.output.write(data)


def request(path, method='GET', data=None, authenticated=True, csrf=True, headers=None, raw_body=None):
    body = raw_body if raw_body is not None else json.dumps(data or {}).encode()
    values = {'Host':'127.0.0.1:18080'}
    if authenticated: values['Cookie']='uhi_session='+SESSION
    if method=='POST':
        values.update({'Content-Type':'application/json', 'Content-Length':str(len(body))})
        if csrf: values['X-UHI-CSRF']=SESSION
    values.update(headers or {})
    raw=(method+' '+path+' HTTP/1.0\r\n'+'\r\n'.join(k+': '+v for k,v in values.items())+'\r\n\r\n').encode()
    sock=Socket(raw+(body if method=='POST' else b''))
    UhiDashboardHandler(sock, ('127.0.0.1',12345), SimpleNamespace(server_address=('127.0.0.1',18080), session_token=SESSION))
    header, _, payload=sock.output.getvalue().partition(b'\r\n\r\n')
    code=int(header.split(b' ')[1])
    return code, header.decode(), payload

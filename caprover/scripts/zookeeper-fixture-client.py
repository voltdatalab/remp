"""Dependency-free ZooKeeper 3.4 fixture client, never a production tool.

Implements only connect/create/get/close of the public Jute protocol. The caller
must derive the address from its own UUID-owned isolated Docker container.
No authentication, ACL changes, arbitrary paths or CLI target are supported.
"""
import re,socket,struct

def _buffer(value):
    return struct.pack('>i',len(value))+value

def _exact(sock,n):
    result=b''
    while len(result)<n:
        chunk=sock.recv(n-len(result))
        if not chunk:raise RuntimeError('fixture_connection_closed')
        result+=chunk
    return result

def _frame(sock):
    n=struct.unpack('>i',_exact(sock,4))[0]
    if not 0<n<=1024*1024:raise RuntimeError('fixture_frame_bound')
    return _exact(sock,n)

def _send(sock,data):
    sock.sendall(struct.pack('>i',len(data))+data)

def verify(host,mode,path,value):
    if mode not in ('create','get') or not re.fullmatch(r'/nucleo-hardening-[a-f0-9]{16}',path) or not re.fullmatch(r'fixture-[a-f0-9]{16}',value):
        raise ValueError('fixture_scope_refused')
    expected=value.encode('ascii')
    with socket.create_connection((host,2181),timeout=5) as sock:
        sock.settimeout(5)
        # ConnectRequest: protocolVersion, lastZxidSeen, timeout, sessionId,
        # passwd buffer, readOnly=false. This is not a password login attempt.
        _send(sock,struct.pack('>iqiq',0,0,10000,0)+_buffer(b'\0'*16)+b'\0')
        connected=_frame(sock)
        if len(connected)<20:raise RuntimeError('fixture_bad_connect_response')
        protocol,timeout,session=struct.unpack('>iiq',connected[:16])
        if protocol!=0 or timeout<=0 or session==0:raise RuntimeError('fixture_session_refused')
        xid=0
        def request(op,body):
            nonlocal xid
            xid+=1;_send(sock,struct.pack('>ii',xid,op)+body)
            for _ in range(4):
                answer=_frame(sock)
                if len(answer)<16:raise RuntimeError('fixture_bad_reply')
                rxid,zxid,error=struct.unpack('>iqi',answer[:16])
                if rxid==-1:continue
                if rxid!=xid or error!=0:raise RuntimeError('fixture_request_refused_'+str(error))
                return answer[16:]
            raise RuntimeError('fixture_unexpected_events')
        if mode=='create':
            # Open ACL is restricted to this disposable node/isolated server.
            acl=struct.pack('>ii',1,31)+_buffer(b'world')+_buffer(b'anyone')
            request(1,_buffer(path.encode('ascii'))+_buffer(expected)+acl+struct.pack('>i',0))
        data=request(4,_buffer(path.encode('ascii'))+b'\0')
        if len(data)<4:raise RuntimeError('fixture_bad_data')
        n=struct.unpack('>i',data[:4])[0]
        if n!=len(expected) or data[4:4+n]!=expected:raise RuntimeError('fixture_readback_mismatch')
        request(-11,b'')
        return True

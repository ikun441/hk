import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

@pytest.fixture
def supervisor():
    path=Path(__file__).resolve().parent.parent/'scripts/serve_lan.py'
    spec=importlib.util.spec_from_file_location('lan_supervisor_under_test',path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize('value,expected',[
    ('10.30.163.86','10.30.163.86'),('192.168.1.20','192.168.1.20'),
    ('172.20.1.8','172.20.1.8'),('8.8.8.8',None),('127.0.0.1',None),
    ('198.18.0.1',None),('',None),('2001:db8::1',None)])
def test_private_interface_address(supervisor,monkeypatch,value,expected):
    monkeypatch.setattr(supervisor.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout=value))
    assert supervisor.private_address('en0')==expected


def test_address_change_disconnect_and_reconnect(supervisor,monkeypatch):
    addresses=iter(['10.30.154.32','10.30.163.86',None,'10.30.163.86'])
    monkeypatch.setattr(supervisor,'private_address',lambda interface:next(addresses))
    monkeypatch.setattr(supervisor,'dotenv_values',lambda path:{'HOST':'old','LAN_INTERFACE':'en0'})
    changes=[]
    monkeypatch.setattr(supervisor,'set_key',lambda *args,**kw:changes.append(args[2]))
    monkeypatch.setattr(supervisor.os,'chmod',lambda *a:None)
    monkeypatch.setattr(supervisor.signal,'signal',lambda *a:None)
    children=[]
    def launch(*a,**kw):
        child=SimpleNamespace(pid=len(children)+1,dead=False,host=kw['env']['HOST'])
        child.poll=lambda:0 if child.dead else None
        child.terminate=lambda:setattr(child,'dead',True)
        child.wait=lambda **kw:0
        children.append(child)
        return child
    monkeypatch.setattr(supervisor.subprocess,'Popen',launch)
    ticks=[]
    def tick(seconds):
        ticks.append(seconds)
        if len(ticks)==4:supervisor.request_stop(None,None)
    monkeypatch.setattr(supervisor.time,'sleep',tick)
    supervisor.main()
    assert [c.host for c in children]==['10.30.154.32','10.30.163.86','10.30.163.86']
    assert changes==['10.30.154.32','10.30.163.86','10.30.163.86']
    assert all(c.dead for c in children)


def test_interface_resolution_failure(supervisor,monkeypatch):
    def fail(*args,**kw):
        raise supervisor.subprocess.TimeoutExpired('ipconfig',5)
    monkeypatch.setattr(supervisor.subprocess,'run',fail)
    assert supervisor.private_address('en0') is None

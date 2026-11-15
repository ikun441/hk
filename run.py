import ipaddress
import os
from dotenv import load_dotenv
import uvicorn
load_dotenv()
if __name__=='__main__':
    host=os.getenv('HOST','127.0.0.1')
    try:
        address=ipaddress.ip_address(host)
    except ValueError:
        raise SystemExit('HOST 必须为明确的回环或私网 IP 地址')
    private=(address.is_loopback or (address.version==4 and any(address in ipaddress.ip_network(n) for n in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'])) or (address.version==6 and address in ipaddress.ip_network('fc00::/7')))
    if not private:
        raise SystemExit('仅允许绑定明确的回环或私网 IP，禁止通配地址和公网 IP')
    uvicorn.run('app.main:app',host=host,port=int(os.getenv('PORT','8000')),workers=1,proxy_headers=False)

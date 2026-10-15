#!/usr/bin/env python3
"""Read-only preflight: kernel / driver build readiness, NOT hardware compatibility."""
import argparse,json,pathlib,re,sys

REQUIRED = ('ARM','MODULES','MMC','MMC_SUNXI','NET','NETDEVICES','WLAN','CFG80211','OF','FW_LOADER')

def get_config(path):
    out={}
    if not path.is_file():return out
    for line in path.read_text(errors='replace').splitlines():
        m=re.fullmatch(r'CONFIG_(\w+)=(.*)',line)
        if m:out[m.group(1)]=m.group(2)
        m=re.fullmatch(r'# CONFIG_(\w+) is not set',line)
        if m:out[m.group(1)]='n'
    return out

def review(configfile,driver,output,source_dir=None):
    c=get_config(configfile)
    reasons=[]
    if not configfile.is_file(): reasons.append('No compiled target kernel .config; no Kbuild possible')
    for x in REQUIRED:
        if c.get(x)!='y':reasons.append(f'CONFIG_{x}={c.get(x,"missing")}; need =y')
    if source_dir and not (source_dir/'Makefile').is_file():reasons.append('Kernel source Makefile missing')
    if not (driver/'os_dep/linux/sdio_intf.c').is_file():reasons.append('RTL8733BS driver source not downloaded')
    else:
        t=(driver/'os_dep/linux/sdio_intf.c').read_text(errors='replace')
        for id in ('0xB733','0xB73A'):
            if id.lower() not in t.lower():reasons.append('SDIO ID missing: '+id)
    mark=driver/'M6_OFFLINE_DRIVER_FORK.json'
    if not mark.is_file():reasons.append('Driver has not been adapted through prepare_vendor_driver_v8.py')
    else:
        j=json.loads(mark.read_text())
        if not j.get('pinned_driver_commit'):reasons.append('Missing upstream driver commit proof')
    make=(driver/'Makefile')
    if make.is_file():
        s=make.read_text(errors='replace')
        if not re.search(r'^CONFIG_PLATFORM_I386_PC\s*=\s*n\s*$',s,re.M):reasons.append('Driver defaults to x86 or unknown platform')
        if not re.search(r'^CONFIG_PLATFORM_ARM_SUN50IW1P1\s*=\s*y\s*$',s,re.M):reasons.append('ARM Sunxi platform branch has not been selected')
    data={'purpose':'Source/Kbuild read-only build gate','kernel_config':str(configfile),'driver_dir':str(driver),
          'required_kernel_flags':{f'CONFIG_{x}':c.get(x,'missing') for x in REQUIRED},
          'build_preflight_passed':not reasons,'issues':reasons,
          'driver_compiled_for_target':False,'board_device_tree_verified':False,
          'M6_flash_backup_verified':False,'safe_to_flash':False}
    if output:output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
    return data

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--kernel-config',type=pathlib.Path,required=True)
    p.add_argument('--kernel-source',type=pathlib.Path)
    p.add_argument('--driver',type=pathlib.Path,required=True)
    p.add_argument('--out',type=pathlib.Path)
    a=p.parse_args()
    d=review(a.kernel_config,a.driver,a.out,a.kernel_source)
    print(json.dumps(d,indent=2,ensure_ascii=False))
    sys.exit(0 if d['build_preflight_passed'] else 3)

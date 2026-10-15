#!/usr/bin/env python3
"""Copy + minimally reconfigure upstream RTL8733BS source for ARM32 lab build.
Does NOT produce a working kernel module without a target kernel Kbuild tree.
Does NOT touch any hardware, flash, or /dev entries.
"""
import argparse, json, pathlib, re, shutil, subprocess, sys
PINS=pathlib.Path(__file__).resolve().parents[1]/'profiles/v8_source_pins.json'

def prepare(source: pathlib.Path, dest: pathlib.Path, patch: pathlib.Path|None, verify_git: bool=True):
    source=source.resolve(); dest=dest.resolve()
    if not (source/'Makefile').is_file() or not (source/'os_dep/linux/sdio_intf.c').is_file():
        raise ValueError('Not the RTL8733BS source tree: Makefile or SDIO entry point missing')
    if dest.exists() or dest==source or source in dest.parents:
        raise ValueError('Destination must be new and outside source directory')
    pins=json.loads(PINS.read_text())
    if verify_git:
        rev=subprocess.run(['git','-C',str(source),'rev-parse','HEAD'],capture_output=True,text=True)
        if rev.returncode or rev.stdout.strip()!=pins['driver']['commit']:
            raise ValueError('Driver checkout does not match pinned commit; use --no-verify-git only for a trusted source copy')
    shutil.copytree(source,dest,ignore=shutil.ignore_patterns('.git','*.o','*.ko','*.mod*','*.cmd'))
    makefile=dest/'Makefile'
    data=makefile.read_text(encoding='utf-8')
    data = data.replace('EXTRA_CFLAGS += -DCONFIG_RESUME_IN_WORKQUEUE', '# CONFIG_RESUME_IN_WORKQUEUE disabled for ARM32 research', 1)
    changes=[
        (r'^CONFIG_PLATFORM_I386_PC\s*=\s*y\s*$', 'CONFIG_PLATFORM_I386_PC = n'),
        (r'^CONFIG_PLATFORM_ARM_SUN50IW1P1\s*=\s*n\s*$', 'CONFIG_PLATFORM_ARM_SUN50IW1P1 = n')
    ]
    for pattern,replacement in changes:
        data,n=re.subn(pattern,replacement,data,count=1,flags=re.M)
        if n!=1: raise ValueError('Unexpected upstream Makefile layout, no safe automatic patch')
    makefile.write_text(data,encoding='utf-8')
    if patch:
        patch=patch.resolve()
        if not patch.is_file(): raise ValueError('CatPlay compatibility patch not found')
        r=subprocess.run(['patch','--batch','--forward','-p1','-i',str(patch)],cwd=dest,text=True,capture_output=True)
        if r.returncode:
            raise RuntimeError('CatPlay patch failed; do not reuse half-patched copy: '+r.stdout[-900:]+r.stderr[-900:])
    marker={
      'purpose':'EXPERIMENTAL ARM32 driver SOURCE only — NOT installable firmware',
      'pinned_driver_commit':pins['driver']['commit'],
      'source_origin':str(source),
      'changes':['CONFIG_PLATFORM_I386_PC=n','CONFIG_PLATFORM_ARM_SUN50IW1P1=y'],
      'patched_for_linux_7_x': bool(patch),
      'runtime_verified':False,'safe_to_flash':False,
      'warning':'Upstream SUN50IW1P1 is ARM64-oriented; Kbuild must force ARCH=arm and explicit CROSS_COMPILE. Hardware pinctrl/regulators not verified.'
    }
    (dest/'M6_OFFLINE_DRIVER_FORK.json').write_text(json.dumps(marker,indent=2,ensure_ascii=False)+'\n')
    return marker

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--source',type=pathlib.Path,required=True)
    p.add_argument('--dest',type=pathlib.Path,required=True)
    p.add_argument('--patch',type=pathlib.Path)
    p.add_argument('--no-verify-git',action='store_true',help='Local fixture only; do not use for release')
    a=p.parse_args()
    try: print(json.dumps(prepare(a.source,a.dest,a.patch,not a.no_verify_git),indent=2,ensure_ascii=False))
    except Exception as e: print('BLOCKED:',e,file=sys.stderr);sys.exit(2)

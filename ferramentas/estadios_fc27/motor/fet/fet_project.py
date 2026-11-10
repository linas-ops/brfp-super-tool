"""Conservative FETP-v4 inventory and explicit record patcher. Python 3.10+, stdlib only.

This edits container records, not the game-specific objects inside their payloads.
Use validated payloads produced by the matching editor/SDK. Never overwrites files.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import uuid
import fetp_v4 as f

KINDS={'ebx':'ebx','res':'resources','chunk':'chunks'}
FIELDS={'name','id','type','partition','restype','resrid','resmeta','patch','original_sha1',
        'addedbundles','links','logical_offset','logical_size','h32','superbundlehash',
        'legacyhash','legacyname','brthash','brtpath','parentbrtpath','original_size',
        'compression_level','is_added','bundle_assignment_only','bundle_ref_only','direct',
        'shader_registrations'}
COMMON={'is_added','original_sha1','patch','addedbundles','bundle_assignment_only','original_size','compression_level'}
KIND_FIELDS={
    'chunk':COMMON|{'id','logical_offset','logical_size','h32','superbundlehash','legacyhash','legacyname'},
    'res':COMMON|{'name','direct','links','restype','resrid','resmeta','shader_registrations'},
    'ebx':COMMON|{'name','direct','links','type','partition','brthash','brtpath','parentbrtpath','bundle_ref_only'}
}

def sha(data):return hashlib.sha256(data).hexdigest()

def file_sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def canonical_key(kind,value):
    if kind=='chunk':return str(uuid.UUID(str(value)))
    if not isinstance(value,str) or not value or '\0' in value:raise ValueError('Asset name must be nonempty and contain no NUL')
    return value.lower()

def record_sha(project,record):return sha(project['bytes'][record['record_start']:record['record_end']])

def riff_identity(raw):
    """Read the observed RIFF/EFIX identity layout only; never edit or infer schemas."""
    if len(raw)<12 or raw[:4]!=b'RIFF' or raw[8:12] not in (b'EBX\0',b'EBXS'):
        raise ValueError('Unsupported EBX representation; expected RIFF EBX/EBXS')
    if struct.unpack_from('<I',raw,4)[0]+8!=len(raw):raise ValueError('RIFF size mismatch')
    chunks={};pos=12
    while pos<len(raw):
        if pos+8>len(raw):raise ValueError('Truncated RIFF chunk')
        tag=raw[pos:pos+4];size=struct.unpack_from('<I',raw,pos+4)[0];end=pos+8+size
        if end+(size&1)>len(raw):raise ValueError('RIFF chunk out of bounds')
        if tag in chunks:raise ValueError('Repeated RIFF chunk')
        chunks[tag]=(pos+8,raw[pos+8:end]);pos=end+(size&1)
    if b'EFIX' not in chunks or b'EBXD' not in chunks:raise ValueError('Missing EFIX/EBXD')
    r=f.Reader(chunks[b'EFIX'][1]);partition=r.guid()
    def array(width):
        n=r.u(4)
        if n>(len(r.data)-r.pos)//width:raise ValueError('EFIX count exceeds chunk bounds')
        return [r.take(width) for _ in range(n)]
    array(16);array(4);exported=r.u(4);instances=[int.from_bytes(v,'little') for v in array(4)]
    array(4);array(4);array(32);array(4);array(4)
    r.u(4);r.u(4);string_offset=r.u(4)
    start,content=chunks[b'EBXD'];padding=(-start)%16;payload=content[padding:]
    if exported>len(instances) or not instances:raise ValueError('Invalid EFIX instance/export counts')
    if not 0<=string_offset<len(payload):raise ValueError('Invalid root string offset')
    end=payload.find(b'\0',string_offset)
    if end<0:raise ValueError('Unterminated root name')
    name=payload[string_offset:end].decode('utf8')
    exports=[]
    for offset in instances[:exported]:
        if not 16<=offset<=len(payload)-8:raise ValueError('Export outside EBXD')
        exports.append(str(uuid.UUID(bytes_le=payload[offset-16:offset])))
    if len(exports)!=len(set(exports)):raise ValueError('Repeated export GUID inside one partition')
    return {'name':name,'partition':partition,'exports':exports}

def bind_profile(args,project):
    if not args.identity_profile:return None
    if not args.cache or not args.sdk:raise ValueError('Identity profile requires --cache and --sdk for exact hash binding')
    profile=json.loads(Path(args.identity_profile).read_text(encoding='utf-8-sig'))
    if profile.get('schema')!=1:raise ValueError('Unsupported identity-profile schema')
    for label in ('cache','sdk'):
        if file_sha(getattr(args,label))!=profile[label+'_sha256']:
            raise ValueError(label+' hash differs from the identity profile; revalidate the profile for this build')
    header=project['header']
    if header['game']!=profile['game'] or header['version']!=profile['editor_version']:
        raise ValueError('Game/editor version differs from the identity profile')
    return profile

def audit(project,profile=None):
    result=f.audit_project(project)
    result=dict(result)
    result['errors']=list(result['errors']);result['warnings']=list(result['warnings'])
    result['container_valid_before_identity_checks']=result['container_valid']
    identities=[];rule_checks=[];skipped=[]
    rules={r['type']:r for r in profile['rules']} if profile else {}
    for e in project['ebx']:
        if not e['flags']&1 or not e['flags']&2:continue
        if e['type'] in rules:
            rule=rules[e['type']]
            if rule['partition_strategy']!='md5-name-lower-utf8-guid-le':raise ValueError('Unsupported partition strategy')
            expected=str(uuid.UUID(bytes_le=hashlib.md5(e['name'].lower().encode('utf8')).digest()))
            ok=e['partition']==expected
            rule_checks.append({'name':e['name'],'type':e['type'],'expected_partition':expected,'actual_partition':e['partition'],'ok':ok})
            if not ok:result['errors'].append('Name-derived partition mismatch: '+e['name'])
        encoded=project['bytes'][e['data_offset']:e['data_offset']+e['data_size']]
        # Only None blocks can be decoded without external codecs. The container
        # audit checks every frame; do not run arbitrary/native decompressor code.
        pos=0;codecs=set()
        while pos<len(encoded):
            if pos+8>len(encoded):break
            a,b=struct.unpack_from('>II',encoded,pos);codecs.add(b>>24);pos+=8+(b&0xfffff)
        if codecs!={0}:
            skipped.append(e['name']);continue
        try:
            identity=riff_identity(f.decompress_none(encoded))
            if identity['name']!=e['name']:raise ValueError('Root Name differs from container record')
            if identity['partition']!=e['partition']:raise ValueError('EFIX partition differs from container record')
            identities.append({'name':e['name'],'exports':len(identity['exports']),'partition':identity['partition']})
        except ValueError as ex:result['errors'].append(e['name']+': '+str(ex))
    if skipped:result['warnings'].append(f'{len(skipped)} added EBX payload identities not decoded: external codec required')
    if not profile:result['warnings'].append('Name-derived lookup rules were not checked: no bound identity profile')
    result['container_valid']=result['container_valid_before_identity_checks']
    result['checks_passed']=not result['errors']
    result['profile_name_checks']=rule_checks
    result['embedded_ebx_identities_checked']=len(identities)
    result['embedded_ebx_identities_skipped']=skipped
    result['semantic_dependencies_validated']=False
    result['game_tested']=False
    return result

def inventory(project,report):
    entries={}
    for kind,section in KINDS.items():
        entries[kind]=[]
        for e in project[section]:
            item={k:e[k] for k in ('name','id','type','partition','resrid','restype','flags','addedbundles','sha1','original_sha1','data_size','legacyhash') if k in e}
            item['record_sha256']=record_sha(project,e);entries[kind].append(item)
    return {'sha256':project['sha256'],'bytes':len(project['bytes']),'header':project['header'],
            'addedbundles':project['addedbundles'],'shader_sources':project['shadersources'],
            'validation':report,'records':entries}

def payload_from_plan(spec,base):
    if set(spec)!={'path','encoding','sha256'}:raise ValueError('Payload requires exactly path, encoding, sha256')
    path=Path(spec['path']);path=path if path.is_absolute() else base/path
    data=path.read_bytes()
    if sha(data)!=spec['sha256']:raise ValueError('Payload SHA256 mismatch: '+str(path))
    if spec['encoding'] not in ('raw','cas'):raise ValueError('Payload encoding must be raw or cas')
    return ('raw' if spec['encoding']=='raw' else 'encoded'),data

def assemble(source,plan,mode,base):
    allowed={'schema','source_sha256','changes','added_bundles','shader_sources'}
    if set(plan)-allowed:raise ValueError('Unknown plan fields: '+str(set(plan)-allowed))
    if plan.get('schema')!=1 or plan.get('source_sha256')!=source['sha256']:raise ValueError('Plan schema/input SHA256 mismatch')
    if mode=='create' and any(source[k] for k in ('chunks','resources','ebx','addedbundles','shadersources')):
        raise ValueError('Create mode requires an empty FET template; use edit mode to preserve existing records')
    bykind={kind:{canonical_key(kind,e['id' if kind=='chunk' else 'name']):e for e in source[section]} for kind,section in KINDS.items()}
    replacements={kind:{} for kind in KINDS};changes=[]
    for change in plan.get('changes',[]):
        if set(change)-{'kind','action','key','expected_record_sha256','record','payload'}:raise ValueError('Unknown change fields')
        kind=change['kind'];action=change['action']
        if kind not in KINDS or action not in ('replace','add','remove'):raise ValueError('Invalid change kind/action')
        key=canonical_key(kind,change['key'])
        if key in replacements[kind]:raise ValueError('Repeated change for one identity')
        exists=key in bykind[kind]
        if (action=='add' and exists) or (action!='add' and not exists):raise ValueError('Add/replace/remove conflicts with existing identity: '+key)
        old=bykind[kind].get(key)
        if old and change.get('expected_record_sha256')!=record_sha(source,old):raise ValueError('Expected record hash mismatch: '+key)
        if action=='remove':
            if 'record' in change or 'payload' in change:raise ValueError('Remove must not contain record/payload')
            replacements[kind][key]=None;changes.append({'kind':kind,'key':key,'action':action});continue
        supplied=change.get('record',{})
        if set(supplied)-KIND_FIELDS[kind]:raise ValueError('Unsupported fields for '+kind+': '+str(set(supplied)-KIND_FIELDS[kind]))
        for field in ('is_added','direct','bundle_assignment_only','bundle_ref_only'):
            if field in supplied and not isinstance(supplied[field],bool):raise ValueError(field+' must be a JSON boolean')
        record=f.asset_from_record(source,old) if old else {}
        if not old and not isinstance(supplied.get('is_added'),bool):raise ValueError('Add requires explicit boolean is_added')
        record.update(supplied)
        if not record.get('is_added',True):
            excluded={'type','partition'} if kind=='ebx' else {'restype','resrid'} if kind=='res' else set()
            if excluded&set(supplied):raise ValueError('Existing-record identity metadata is not stored here: '+str(excluded&set(supplied)))
        identity_field='id' if kind=='chunk' else 'name'
        if identity_field not in record or canonical_key(kind,record[identity_field])!=key:
            raise ValueError('Record identity differs from key; model a rename as remove+add with remapped dependencies')
        if 'payload' in change:
            record.pop('encoded',None);record.pop('raw',None)
            payload_kind,bytes_=payload_from_plan(change['payload'],base);record[payload_kind]=bytes_
            if payload_kind=='raw':record.pop('original_size',None);record.pop('compression_level',None)
        replacements[kind][key]=record
        changes.append({'kind':kind,'key':key,'action':action,'payload_sha256':sha(record.get('raw',record.get('encoded',b'')))})
    bundles=source['addedbundles']+plan.get('added_bundles',[])
    shader_sources=list(source['shadersources'])
    for key in plan.get('shader_sources',[]):
        if key not in shader_sources:shader_sources.append(key)
    for entry in replacements['res'].values():
        if entry:
            for _,key in entry.get('shader_registrations',[]):
                if key not in shader_sources:shader_sources.append(key)
    indices={key:i for i,key in enumerate(shader_sources)}
    out=bytearray(source['bytes'][:source['header']['end']]);out+=f.uint(len(bundles),3)
    for b in bundles:
        if set(b)!={'name','superbundle','type'}:raise ValueError('Bundle requires name, superbundle, type')
        out+=f.string(b['name'])+f.uint(b['superbundle'],4)+f.uint(b['type'])
    for kind,section in (('chunk','chunks'),('res','resources'),('ebx','ebx')):
        if kind=='ebx':out+=f.bundles(shader_sources)
        rows=[];seen=set()
        def encode(record):
            writer={'chunk':f.write_chunk,'res':f.write_res,'ebx':f.write_ebx}[kind]
            return writer(record,source['header']['patch'],indices) if kind=='res' else writer(record,source['header']['patch'])
        for old in source[section]:
            key=canonical_key(kind,old['id' if kind=='chunk' else 'name']);seen.add(key)
            if key not in replacements[kind]:rows.append(source['bytes'][old['record_start']:old['record_end']])
            elif replacements[kind][key] is not None:rows.append(encode(replacements[kind][key]))
        for key,entry in replacements[kind].items():
            if key not in seen:rows.append(encode(entry))
        out+=f.uint(len(rows),3)+b''.join(rows)
    return bytes(out),changes

def emit(data,path=None):
    text=json.dumps(data,indent=2,ensure_ascii=False)
    if path:
        with Path(path).open('x',encoding='utf8') as stream:stream.write(text+'\n')
    return text

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for command in ('inspect','apply','create'):
        p=sub.add_parser(command);p.add_argument('source');p.add_argument('--report')
        p.add_argument('--identity-profile');p.add_argument('--cache');p.add_argument('--sdk')
        if command in ('apply','create'):p.add_argument('output')
        if command=='apply':p.add_argument('--plan',required=True);p.add_argument('--mode',choices=('edit','create'),required=True)
    args=parser.parse_args(argv)
    # A report path is also no-clobber; detect conflicts before publishing output.
    if args.report and Path(args.report).exists():raise ValueError('Report already exists')
    source=f.read_project(args.source);profile=bind_profile(args,source);report=audit(source,profile)
    if args.command=='inspect':
        output=inventory(source,report)
        if args.report:emit(output,args.report)
        print(json.dumps({'sha256':source['sha256'],'header':source['header'],'report':args.report,'validation':report},indent=2,ensure_ascii=False))
        return 0 if report['checks_passed'] else 1
    output_path=Path(args.output).resolve();source_path=Path(args.source).resolve()
    if output_path==source_path or output_path.exists():raise ValueError('Output must be a new file different from source')
    if args.report and Path(args.report).resolve() in (source_path,output_path):raise ValueError('Report path conflicts with project path')
    if not report['container_valid_before_identity_checks']:raise ValueError('Source container audit failed; repair using the matching editor or investigated codec: '+str(report['errors'][:5]))
    if args.command=='create':plan={'schema':1,'source_sha256':source['sha256'],'changes':[]};mode='create';base=source_path.parent
    else:
        planpath=Path(args.plan).resolve();plan=json.loads(planpath.read_text(encoding='utf-8-sig'));base=planpath.parent;mode=args.mode
    candidate,changes=assemble(source,plan,mode,base)
    output_path.parent.mkdir(parents=True,exist_ok=True)
    parsed=f.read_project_bytes(candidate)
    candidate_report=audit(parsed,profile)
    if not candidate_report['checks_passed']:raise ValueError('Candidate audit failed: '+str(candidate_report['errors'][:8]))
    if file_sha(source_path)!=source['sha256']:raise ValueError('Source changed during preparation; no output published')
    final=f.publish_project_bytes(candidate,output_path,expected_header=source['bytes'][:source['header']['end']])
    result={'output':str(output_path),'sha256':final['sha256'],'source_sha256':source['sha256'],'mode':mode,
            'changes':changes,'validation':candidate_report,'original_preserved':True,'editor_reopened':False,'mod_exported':False,'game_tested':False}
    print(emit(result,args.report));return 0

if __name__=='__main__':
    try:sys.exit(main())
    except (ValueError,KeyError,IndexError,TypeError,OSError,struct.error) as ex:
        print(json.dumps({'ok':False,'error':str(ex)},ensure_ascii=False),file=sys.stderr);sys.exit(2)

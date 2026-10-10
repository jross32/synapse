import { useEffect, useState } from 'react';
import { ChevronDown, ChevronRight, Image as ImageIcon } from 'lucide-react';
import { listProjectDesignReferences, type ProjectDesignReference } from '@shared/design-references-client';
import { Button } from './ui/button';

export function ProjectDesignReferences({projectId}:{projectId:string}):JSX.Element|null {
 const [refs,setRefs]=useState<ProjectDesignReference[]>([]); const [open,setOpen]=useState(false);
 useEffect(()=>{let stop=false; void listProjectDesignReferences(projectId).then(x=>!stop&&setRefs(x)).catch(()=>!stop&&setRefs([])); return()=>{stop=true}},[projectId]);
 const current=refs.find(r=>r.role==='proposed_ui'&&r.is_current)??refs.find(r=>r.role==='proposed_ui');
 if(!current) return null;
 return <div className='rounded-xl border border-border bg-secondary/20'>
  <Button variant='ghost' className='h-auto w-full justify-between rounded-xl px-4 py-3' onClick={()=>setOpen(v=>!v)} aria-expanded={open}>
   <span className='flex items-center gap-2'><ImageIcon className='h-4 w-4 text-primary'/><span className='text-left'><span className='block text-sm font-semibold'>Current proposed UI</span><span className='block text-xs font-normal text-muted-foreground'>{current.title}</span></span></span>
   {open?<ChevronDown className='h-4 w-4'/>:<ChevronRight className='h-4 w-4'/>}
  </Button>
  {open&&<div className='border-t border-border p-4'>
    <img src={current.url} alt={current.title} className='max-h-[520px] w-full rounded-lg border border-border object-contain bg-black/20'/>
    {current.description&&<p className='mt-3 text-sm text-muted-foreground'>{current.description}</p>}
    <p className='mt-2 text-xs text-muted-foreground'>AI-visible design reference · {refs.length} saved reference{refs.length===1?'':'s'}</p>
  </div>}
 </div>
}

import { apiFetch } from './api-client';
export interface ProjectDesignReference {
 id:string; project_id:string; file_id:string; role:string; title:string; description:string|null;
 is_current:boolean; ai_visible:boolean; original_name:string; mime:string; size_bytes:number; url:string;
}
export async function listProjectDesignReferences(projectId:string):Promise<ProjectDesignReference[]>{
 return (await apiFetch<{references:ProjectDesignReference[]}>(`/projects/${encodeURIComponent(projectId)}/design-references`)).references;
}

'use strict';
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('synapseInstaller',{
 preflight:()=>ipcRenderer.invoke('setup:preflight'),
 install:()=>ipcRenderer.invoke('setup:install'),
 launch:()=>ipcRenderer.invoke('setup:launch'),
 windowAction:(action)=>ipcRenderer.invoke('setup:window',action),
 onStatus:(fn)=>{const listener=(_event,status)=>fn(status);ipcRenderer.on('setup:status',listener);return ()=>ipcRenderer.removeListener('setup:status',listener)}
});

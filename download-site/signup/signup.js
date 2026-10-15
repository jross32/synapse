"use strict";
const form=document.getElementById("signup-form");
const status=document.getElementById("signup-status");
const button=document.getElementById("submit-signup");
form.addEventListener("submit",async event=>{
 event.preventDefault();
 const data=new FormData(form);
 if(data.get("password")!==data.get("confirm")){status.textContent="Passwords do not match.";return}
 button.disabled=true;status.textContent="Creating your account?";
 try{
  const controller=new AbortController();
  const timeout=setTimeout(()=>controller.abort(),12000);
  let response;
  try{response=await fetch("https://accounts-api-production-f84a.up.railway.app/v1/auth/signup",{
   method:"POST",headers:{"Content-Type":"application/json"},
   body:JSON.stringify({username:data.get("username"),email:data.get("email"),password:data.get("password")}),
   credentials:"omit",cache:"no-store",signal:controller.signal
  })}finally{clearTimeout(timeout)}
  if(!response.ok){
   const detail=await response.json().catch(()=>({}));
   const message=typeof detail.detail==="string" ? detail.detail : "Please check your details and try again.";
   status.textContent=response.status===409 ? "This username or email is already registered." : response.status===429 ? "Too many attempts. Please try later." : response.status>=500 ? "Account service is temporarily unavailable." : message;
   return;
  }
  // Do not store or log bearer tokens in browser storage, URLs, or analytics.
  form.reset();form.hidden=true;
  status.textContent="Account created. Download Synapse, open it, and sign in with your new account.";
  const link=document.createElement("a");link.href="/start";link.textContent="Continue to installation";link.className="btn btn-primary";status.append(" ",link);
 }catch(e){status.textContent="Cannot reach the account service. Please try again later or create your account inside the desktop app."}
 finally{button.disabled=false}
});

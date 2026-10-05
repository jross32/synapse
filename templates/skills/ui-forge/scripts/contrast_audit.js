(() => {
 const parse=(s)=>{
  const m=String(s||"").match(/rgba?\((\d+)\D+(\d+)\D+(\d+)(?:\D+([\d.]+))?\)/i);
  return m?[+m[1],+m[2],+m[3],m[4]==null?1:+m[4]]:null;
 };
 const blend=(fg,bg)=>{const a=fg[3]+bg[3]*(1-fg[3]); return [0,1,2].map(i=>(fg[i]*fg[3]+bg[i]*bg[3]*(1-fg[3]))/a).concat(a)};
 const opaqueBg=(el)=>{
  let out=[255,255,255,1], chain=[]; for(let n=el;n&&n.nodeType===1;n=n.parentElement) chain.push(n);
  for(const n of chain.reverse()){const c=parse(getComputedStyle(n).backgroundColor); if(c&&c[3]>0) out=blend(c,out)}
  return out;
 };
 const lum=(c)=>{const f=x=>{x/=255;return x<=.04045?x/12.92:Math.pow((x+.055)/1.055,2.4)}; return .2126*f(c[0])+.7152*f(c[1])+.0722*f(c[2])};
 const ratio=(a,b)=>{const x=lum(a),y=lum(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05)};
 const rows=[];
 for(const el of document.querySelectorAll("body *")){
  const text=Array.from(el.childNodes).filter(n=>n.nodeType===3).map(n=>n.nodeValue).join("").trim(); if(!text) continue;
  const cs=getComputedStyle(el); if(cs.display==="none"||cs.visibility==="hidden") continue;
  const fg=parse(cs.color), bg=opaqueBg(el); if(!fg) continue;
  const finalFg=fg[3]<1?blend(fg,bg):fg, r=ratio(finalFg,bg), size=parseFloat(cs.fontSize)||16, weight=parseInt(cs.fontWeight)||400;
  const large=size>=24||(size>=18.66&&weight>=700), required=large?3:4.5;
  rows.push({tag:el.tagName.toLowerCase(),text:text.slice(0,100),ratio:+r.toFixed(2),required,pass:r>=required,font_size:size,font_weight:weight});
 }
 return {schema:"ui-forge-contrast-audit-v1",checked:rows.length,failures:rows.filter(x=>!x.pass),rows};
})()

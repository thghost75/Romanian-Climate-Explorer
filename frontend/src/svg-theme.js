// SVG downloads cannot see the page stylesheet. Freeze the displayed palette.
export function inlineSVGTheme(source, clone) {
 const selector='text,line,path,circle,rect,stop,polygon';
 const originals=source.querySelectorAll(selector), copies=clone.querySelectorAll(selector);
 originals.forEach((element,index)=>{
  const style=getComputedStyle(element);
  for(const key of ['fill','stroke','stop-color','font-family','font-size','font-weight']){
   const value=style.getPropertyValue(key);
   // Keep local gradient IDs instead of computed absolute document URLs.
   if(value&&!value.startsWith('url('))copies[index].setAttribute(key,value);
  }
 });
}

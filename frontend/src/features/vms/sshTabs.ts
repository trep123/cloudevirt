export function addSSHTab(tabs:number[], id:number, limit:number):number[] {
  if(!Number.isSafeInteger(id) || id<1 || tabs.includes(id) || tabs.length>=limit)return tabs;
  return [...tabs,id];
}
export function closeSSHTab(tabs:number[],active:number,id:number) {
  const index=tabs.indexOf(id);
  const next=tabs.filter(value=>value!==id);
  return {tabs:next,active:active===id?(next[Math.min(Math.max(0,index),next.length-1)]||0):active};
}

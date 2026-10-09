export async function analyze(file,params,signal) {
  const form=new FormData(); form.append('file',file,file.name);
  for(const [key,value] of Object.entries(params)) form.append(key,String(value));
  const response=await fetch('/api/analyze',{method:'POST',body:form,signal});
  let result;
  try { result=await response.json(); } catch { throw new Error(`Invalid server response (HTTP ${response.status}).`); }
  if(!response.ok) throw new Error(result.error||`HTTP ${response.status}`);
  if(!['COMPLETE','PARTIAL'].includes(result.status)||!Array.isArray(result.frequency_hz)||!Array.isArray(result.psd_dbfs_per_hz)||!result.power_metrics) throw new Error('Incomplete analysis response.');
  return result;
}

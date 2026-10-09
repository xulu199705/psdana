export const state = {
  mode:'psd', file:null, status:'NO FILE', result:null, stale:false, message:'',
  revision:0, controller:null, editing:false,
  params:{sample_rate_hz:160e6,power_band_left_hz:-20e6,power_band_right_hz:20e6,symbol_rate_hz:20e6,rrc_beta:.25},
};

export function selectFile(file) {
  state.controller?.abort();
  state.controller=null;
  state.revision++;
  state.result=null; state.stale=false; state.message='';
  state.file=file; state.status=file?'FILE READY':'NO FILE';
}

export function changeParameter(key,value) {
  if (Object.is(state.params[key],value)) return;
  state.params[key]=value;
  state.controller?.abort(); state.controller=null; state.revision++;
  state.stale=!!state.result;
  state.status=state.file?'FILE READY':'NO FILE'; state.message='';
}

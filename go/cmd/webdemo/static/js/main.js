import {state,selectFile} from './state.js';
import {analyze} from './api.js';
import {validate,editable,bindEditors} from './parameters.js';
import {fitViewport} from './responsive.js';
import {psdOption} from './charts/psd.js';
import {qamOption} from './charts/qam.js';

const $=id=>document.getElementById(id);
let scale=1;
const chart=echarts.init($('chart'),null,{renderer:'canvas'});
const number=(v,digits=2)=>Number.isFinite(v)?v.toFixed(digits).replace('-','−'):'N/A';
const db=v=>v===null?'−∞':number(v);
function field(label,content,unit='',band=false) {
  const wrapper=document.createElement('div'); wrapper.className='field';
  const heading=document.createElement('p'); heading.className='field-label'; heading.textContent=label;
  const value=document.createElement('div'); value.className=`field-value${band?' band':''}`;
  for(const item of Array.isArray(content)?content:[content]) value.append(item instanceof Node?item:document.createTextNode(item));
  if(unit){const suffix=document.createElement('span');suffix.textContent=unit;value.append(suffix);}
  wrapper.append(heading,value);return wrapper;
}
function span(text,className){const e=document.createElement('span');e.textContent=text;e.className=className;return e;}
function auxiliary(items){
  $('auxiliary').replaceChildren(...items.map(([label,value])=>{
    const row=document.createElement('div');row.className='aux-row';const strong=document.createElement('strong');strong.textContent=value;
    row.append(span(label,''),strong);return row;
  }));
}
function renderChart(){
  chart.resize();
  chart.setOption(state.mode==='psd'?psdOption(state.result,scale):qamOption(state.result?.qam_metrics,scale),{notMerge:true});
}
function render() {
  const isPSD=state.mode==='psd',r=state.result,q=r?.qam_metrics,p=r?.power_metrics;
  $('title').textContent=isPSD?'频谱分析':'星座分析';
  $('subtitle').textContent=isPSD?'POWER SPECTRAL DENSITY':'QAM CONSTELLATION';
  $('signal').textContent=isPSD?'SIGNAL / 01':'SIGNAL / 02';
  $('analysis').setAttribute('aria-labelledby',`tab-${state.mode}`);
  $('chart').setAttribute('aria-label',isPSD?'Power spectral density chart':'QAM constellation chart');
  document.querySelectorAll('[data-mode]').forEach(button=>{const active=button.dataset.mode===state.mode;button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;});
  $('result-mode').hidden=!isPSD;$('legend').hidden=isPSD;
  $('result-label').textContent=state.stale?'RESULTS / STALE':'RESULTS';
  $('primary-label').textContent=isPSD?'AVERAGE POWER':'EVM RMS';
  $('primary-value').textContent=isPSD?(p?db(p.average_power_dbfs):'—'):(q?number(q.evm_pct_rms):'—');
  $('primary-unit').textContent=isPSD?'dBFS':'%';
  auxiliary(isPSD?[['PEAK POWER',p?`${db(p.peak_power_dbfs)} dBFS`:'—']]:[
    ['PHASE ERROR',q?`${number(q.phase_error_pct_rms)} %rms`:'—'],
    ['AMPLITUDE ERROR',q?`${number(q.amplitude_error_pct_rms)} %rms`:'—'],
    ['FREQUENCY ERROR',q?(q.frequency_error_hz===null?'N/A':`${number(q.frequency_error_hz,1)} Hz`):'—'],
  ]);
  if(!state.editing) $('secondary').replaceChildren(...(isPSD?[
    field('PEAK FREQ.',p?(Number.isFinite(p.peak_frequency_hz)?`${p.peak_frequency_hz>=0?'+':''}${number(p.peak_frequency_hz/1e6,3)} MHz`:'N/A'):'—'),
    field('SAMPLE RATE',editable('sample_rate_hz'),'MSPS'),
    field('FFT SIZE',r?String(r.fft_size):'—'),
    field('POWER BAND / MHz',[editable('power_band_left_hz'),span('→','arrow'),editable('power_band_right_hz'),span('MHz','unit')],'',true),
  ]:[
    field('MODULATION','64QAM'),field('SYMBOL RATE',editable('symbol_rate_hz'),'MSym/s'),
    field('SAMPLE RATE',editable('sample_rate_hz'),'MSPS'),field('RRC ROLL-OFF',editable('rrc_beta')),
  ]));
  const invalid=validate(state.params);
  $('analyze').disabled=!state.file||!!invalid||state.status==='PROCESSING';
  $('analyze').textContent=state.status==='PROCESSING'?'ANALYZING…':'ANALYZE';
  $('filename').textContent=state.file?.name||'DROP / SELECT CSV';
  $('choose-file').title=state.file?.name||'Choose a hex_q15 CSV';
  $('status').textContent=state.status+(state.stale?' · STALE':'')+(invalid?' · INVALID PARAMETERS':'');
  const warnings=q?.diagnostics?.warnings;
  const warning=Array.isArray(warnings)?warnings.join(' · '):'';
  const message=invalid||state.message||r?.qam_error||warning||(state.stale?'Parameters changed — click ANALYZE to update.':'');
  $('message').textContent=message;$('message').title=message;
  $('message').classList.toggle('error',!!invalid||state.status==='ERROR');
  renderChart();
}
function choose(file) {
  if(!file)return;
  if(!/\.csv$/i.test(file.name)) {selectFile(null);state.status='ERROR';state.message='Choose one .csv file containing HEX Q1.15 samples.';}
  else if(file.size>16*1024*1024-65536){selectFile(null);state.status='ERROR';state.message='CSV is too large (request limit: 16 MiB including form fields).';}
  else selectFile(file);
  render();
}
$('choose-file').addEventListener('click',()=>$('file-input').click());
$('file-input').addEventListener('change',()=>{choose($('file-input').files[0]);$('file-input').value='';});
document.querySelectorAll('[data-mode]').forEach(button=>{
  button.addEventListener('click',()=>{state.mode=button.dataset.mode;render();});
  button.addEventListener('keydown',event=>{
    if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){
      event.preventDefault(); state.mode=event.key==='Home'?'psd':event.key==='End'?'qam':state.mode==='psd'?'qam':'psd';render();$(`tab-${state.mode}`).focus();
    }
  });
});
bindEditors($('secondary'),render);
$('analyze').addEventListener('click',async()=>{
  if(!state.file||validate(state.params)||state.status==='PROCESSING')return;
  const revision=++state.revision,controller=new AbortController();state.controller=controller;
  state.status='PROCESSING';state.message='';state.result=null;state.stale=false;render();
  try {
    const result=await analyze(state.file,{...state.params},controller.signal);
    if(revision!==state.revision)return;
    state.result=result;state.status=result.status;
  } catch(error) {
    if(revision!==state.revision)return;
    state.result=null;state.status='ERROR';state.message=error.message||'Analysis failed; retry.';
  } finally {
    if(revision===state.revision){state.controller=null;render();}
  }
});
let dragDepth=0;
window.addEventListener('dragenter',event=>{event.preventDefault();if(event.dataTransfer?.types.includes('Files')){dragDepth++;$('drop-overlay').hidden=false;}});
window.addEventListener('dragover',event=>{event.preventDefault();if(event.dataTransfer)event.dataTransfer.dropEffect='copy';});
window.addEventListener('dragleave',event=>{event.preventDefault();dragDepth=Math.max(0,dragDepth-1);if(!dragDepth)$('drop-overlay').hidden=true;});
window.addEventListener('drop',event=>{
  event.preventDefault();dragDepth=0;$('drop-overlay').hidden=true;
  const files=event.dataTransfer?.files;
  if(files?.length>1){state.message='Drop exactly one CSV file at a time.';render();return;}
  choose(files?.[0]);
});
window.addEventListener('blur',()=>{dragDepth=0;$('drop-overlay').hidden=true;});
fitViewport(value=>{scale=value;renderChart();});
document.fonts.ready.then(renderChart);
render();

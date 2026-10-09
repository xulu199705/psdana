import {state,changeParameter} from './state.js';

export function validate(p) {
  if (!Number.isFinite(p.sample_rate_hz)||p.sample_rate_hz<=0) return 'Sample Rate must be finite and positive.';
  if (![p.power_band_left_hz,p.power_band_right_hz].every(Number.isFinite)||p.power_band_left_hz>p.power_band_right_hz) return 'Power Band: lower must be ≤ upper; equal bounds measure one frequency.';
  if (p.power_band_left_hz < -p.sample_rate_hz/2 || p.power_band_right_hz > p.sample_rate_hz/2) return 'Power Band must be within ± Sample Rate / 2.';
  if (!Number.isFinite(p.symbol_rate_hz)||p.symbol_rate_hz<=0) return 'Symbol Rate must be finite and positive.';
  const sps=p.sample_rate_hz/p.symbol_rate_hz;
  if (!Number.isFinite(sps)||sps<2||sps>1e5||Math.abs(sps-Math.round(sps))>8*Number.EPSILON*sps) return 'Sample Rate / Symbol Rate must be integer SPS ≥ 2 (default RRC limit: 100000).';
  if (!Number.isFinite(p.rrc_beta)||p.rrc_beta<0||p.rrc_beta>1) return 'RRC β must be between 0 and 1.';
  if (p.symbol_rate_hz<=10000) return 'Symbol Rate must exceed 0.01 MSym/s for the default ±5000 Hz CFO search.';
  return '';
}

const definitions={sample_rate_hz:['Sample Rate (MSPS)',1e6],symbol_rate_hz:['Symbol Rate (MSym/s)',1e6],power_band_left_hz:['Power Band Lower (MHz)',1e6],power_band_right_hz:['Power Band Upper (MHz)',1e6],rrc_beta:['RRC roll-off',1]};
export function editable(key) {
  const [label,divisor]=definitions[key];
  const value=state.params[key]/divisor;
  const button=document.createElement('button');
  button.className='edit-value'; button.dataset.parameter=key;
  button.setAttribute('aria-label',label);
  button.title=`Edit ${label} · Enter to confirm · Escape to cancel`;
  button.textContent=Number.isFinite(value)?`${key==='power_band_right_hz'&&value>0?'+':''}${value}`:'Invalid';
  return button;
}

export function bindEditors(root,render) {
  root.addEventListener('click',event=>{
    const button=event.target.closest('[data-parameter]');
    if (!button || state.editing) return;
    const key=button.dataset.parameter; const [label,divisor]=definitions[key];
    const input=document.createElement('input');
    input.type='text'; input.inputMode='decimal'; input.className='inline-editor';
    input.setAttribute('aria-label',label); input.value=String(state.params[key]/divisor);
    input.style.width=`${Math.max(42,Math.min(142,input.value.length*11+10))}rem`;
    let finished=false;
    const finish=cancel=>{
      if(finished) return; finished=true; state.editing=false;
      if(!cancel) {
        const token=input.value.trim().replaceAll('−','-');
        const numeric=/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(token)?Number(token)*divisor:NaN;
        changeParameter(key,numeric);
      }
      render(); root.querySelector(`[data-parameter="${key}"]`)?.focus();
    };
    input.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key==='Escape'){e.preventDefault();finish(e.key==='Escape');}});
    input.addEventListener('blur',()=>finish(false));
    state.editing=true; button.replaceWith(input); input.focus(); input.select();
  });
}

import {axis,base} from './common.js';
export function psdOption(result,scale) {
  const frequencies=result?.frequency_hz||[];
  const points=frequencies.map((frequency,i)=>[frequency/1e6,result.psd_dbfs_per_hz[i]??null]);
  const x=axis('FREQUENCY / MHz',scale),y=axis('PSD / dBFS/Hz',scale);
  if(frequencies.length){
    x.min=frequencies[0]/1e6;
    // Extend only the axis to Nyquist, never reorder or change the FFT samples.
    x.max=result.input_type==='complex'?result.fs_hz/2e6:frequencies.at(-1)/1e6;
    x.interval=(x.max-x.min)/4;
    x.axisLabel.formatter=v=>Number(v.toPrecision(5)).toString();
  }
  else {x.min=-80;x.max=80;}
  let low=Infinity,high=-Infinity;
  for(const [,v] of points) if(Number.isFinite(v)){low=Math.min(low,v);high=Math.max(high,v);}
  const step=Number.isFinite(low)?Math.max(20,20*Math.ceil((high-low)/100)):20;
  y.min=Number.isFinite(low)?Math.floor(low/step)*step:-140;
  y.max=Number.isFinite(high)?Math.ceil(high/step)*step:-40;
  if(y.max===y.min)y.max+=step;
  y.interval=step;
  y.splitNumber=5; y.nameGap=48*scale;
  return {...base(scale),xAxis:x,yAxis:y,series:[{type:'line',data:points,symbol:'none',showSymbol:false,smooth:false,connectNulls:false,lineStyle:{color:'#ff684a',width:1.4*scale},emphasis:{disabled:true}}]};
}

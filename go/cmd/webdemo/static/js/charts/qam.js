import {axis,base} from './common.js';
export function qamOption(result,scale) {
  const recovered=(result?.constellation_i||[]).map((i,n)=>[i,result.constellation_q[n]]);
  const ideal=(result?.ideal_i||[]).map((i,n)=>[i,result.ideal_q[n]]);
  let extent=1.5;
  for(const point of [...recovered,...ideal]) for(const v of point) if(Number.isFinite(v))extent=Math.max(extent,Math.ceil(Math.abs(v)*2)/2);
  const x=axis('IN-PHASE / I',scale),y=axis('QUADRATURE / Q',scale);
  for(const a of [x,y]){a.min=-extent;a.max=extent;a.splitNumber=6;}
  y.nameGap=48*scale;
  return {...base(scale),grid:{left:72*scale,top:30*scale,width:378*scale,height:378*scale,outerBoundsMode:'none'},xAxis:x,yAxis:y,
    series:[{name:'Recovered',type:'scatter',data:recovered,symbolSize:3*scale,itemStyle:{color:'#ffd84a',opacity:.55},emphasis:{disabled:true}},
      {name:'Ideal',type:'scatter',data:ideal,symbol:'circle',symbolSize:10*scale,z:3,itemStyle:{color:'transparent',borderColor:'#ff684a',borderWidth:1.5*scale},emphasis:{disabled:true}}]};
}

export function axis(name,scale) {
  return {type:'value',name,nameLocation:'middle',nameGap:38*scale,
    nameTextStyle:{fontFamily:'Noto Sans',fontSize:12*scale,color:'#cbd0d0',fontWeight:500},
    axisLine:{show:true,onZero:false,lineStyle:{color:'#92999b',width:scale}},
    axisTick:{show:false},axisLabel:{fontFamily:'Noto Sans',fontSize:10.5*scale,color:'#cbd0d0',margin:10*scale},
    splitLine:{show:true,lineStyle:{color:'#353d40',width:scale}},splitNumber:4};
}
export function base(scale) {
  return {animation:false,backgroundColor:'#191d20',textStyle:{fontFamily:'Noto Sans'},
    grid:{left:72*scale,top:32*scale,width:384*scale,height:380*scale,outerBoundsMode:'none'},
    tooltip:{show:false}};
}

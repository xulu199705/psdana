export const BASE_WIDTH=540, BASE_HEIGHT=960, MAX_HEIGHT=2160;
export function fitViewport(onResize) {
  let frame;
  const resize=()=>{
    const scale=Math.min(window.innerWidth/BASE_WIDTH,window.innerHeight/BASE_HEIGHT,MAX_HEIGHT/BASE_HEIGHT);
    // rem scales geometry and typography together; chart draws at actual CSS size.
    document.documentElement.style.fontSize=`${scale}px`;
    onResize(scale);
  };
  window.addEventListener('resize',()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(resize);});
  resize();
}

// Vector trace of the supplied Harvestly logo PNG (colour-separated layers, potrace). No redrawing.
const {PNG}=require('pngjs'),potrace=require('potrace'),fs=require('fs');
const SRC=process.env.HOME+'/Downloads/Harvestly Grain Monitoring Logo.png';
const OUT=__dirname+'/../../site/brand';fs.mkdirSync(OUT,{recursive:true});
const C={green:'#09342B',amber:'#CC9033',cream:'#E9DFC0'};
const lum=(r,g,b)=>0.299*r+0.587*g+0.114*b;
const rules={
 green:(r,g,b)=>lum(r,g,b)<150&&!(r-b>70),
 amber:(r,g,b)=>r-b>70&&r>150&&g>95,
 cream:(r,g,b)=>lum(r,g,b)>205&&(r-b)>=16&&(r-b)<70&&r>215&&!(r-b>70),
};
(async()=>{
 const png=PNG.sync.read(fs.readFileSync(SRC));const W=png.width,H=png.height;const data=Buffer.alloc(W*H*3);for(let i=0;i<W*H;i++){data[i*3]=png.data[i*4];data[i*3+1]=png.data[i*4+1];data[i*3+2]=png.data[i*4+2];}
 // region crops (x0,y0,x1,y1); the supplied tagline strip (y>760) is excluded everywhere
 const R={full:[110,420,1160,740],horizontal:[110,420,1160,675],symbol:[110,420,345,712]};
 const trace=(buf,w,h)=>new Promise((res,rej)=>{
   const t=new potrace.Potrace({turdSize:20,optTolerance:0.4,alphaMax:1,turnPolicy:'minority'});
   t.loadImage(buf,e=>{if(e)return rej(e);res(t.getPathTag('#000'))});});
 const layers={};
 for(const [name,[x0,y0,x1,y1]] of Object.entries(R)){
  const w=x1-x0,h=y1-y0;layers[name]={w,h,paths:{}};
  for(const L of ['cream','green','amber']){
   const m=new Float32Array(w*h);
   for(let y=0;y<h;y++)for(let x=0;x<w;x++){const i=((y+y0)*W+x+x0)*3;m[y*w+x]=rules[L](data[i],data[i+1],data[i+2])?1:0;}
   const S=3,uw=w*S,uh=h*S;let u=new Float32Array(uw*uh);
   for(let y=0;y<uh;y++)for(let x=0;x<uw;x++){const fx=Math.min(w-1.001,Math.max(0,(x+.5)/S-.5)),fy=Math.min(h-1.001,Math.max(0,(y+.5)/S-.5));const x1=fx|0,y1=fy|0,ax=fx-x1,ay=fy-y1;
     u[y*uw+x]=m[y1*w+x1]*(1-ax)*(1-ay)+m[y1*w+x1+1]*ax*(1-ay)+m[(y1+1)*w+x1]*(1-ax)*ay+m[(y1+1)*w+x1+1]*ax*ay;}
   for(let pass=0;pass<4;pass++){const v=new Float32Array(uw*uh);for(let y=1;y<uh-1;y++)for(let x=1;x<uw-1;x++){let a=0;for(let dy=-1;dy<=1;dy++)for(let dx=-1;dx<=1;dx++)a+=u[(y+dy)*uw+x+dx];v[y*uw+x]=a/9;}u=v;}
   const out=new PNG({width:uw,height:uh});for(let i=0;i<uw*uh;i++){const b=u[i]>=.5?0:255;out.data[i*4]=out.data[i*4+1]=out.data[i*4+2]=b;out.data[i*4+3]=255;}
   const up=PNG.sync.write(out);
   const tag=await trace(up,w*3,h*3);
   const d=tag.match(/d="([^"]+)"/)[1];
   layers[name].paths[L]=d;
  }
 }
 const svg=(k,pal,bg)=>{const {w,h,paths}=layers[k];
  const pad=Math.round(h*0.04);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${-pad} ${-pad} ${w+2*pad} ${h+2*pad}" role="img" aria-label="Harvestly">`+
  (bg?`<rect x="${-pad}" y="${-pad}" width="${w+2*pad}" height="${h+2*pad}" fill="${bg}"/>`:'')+
  `<g transform="scale(0.3333)">`+['cream','green','amber'].map(L=>paths[L]?`<path fill="${pal[L]}" fill-rule="evenodd" d="${paths[L]}"/>`:'').join('')+`</g></svg>`;};
 const PAL={light:C,dark:{green:'#F7F3EA',amber:'#D9A441',cream:'#3C5A4B'}};
 for(const k of Object.keys(R)){
  fs.writeFileSync(`${OUT}/harvestly-${k}.svg`,svg(k,PAL.light));
  fs.writeFileSync(`${OUT}/harvestly-${k}-reversed.svg`,svg(k,PAL.dark));
 }
 console.log(fs.readdirSync(OUT).map(f=>f+' '+fs.statSync(OUT+'/'+f).size).join('\n'));
})();

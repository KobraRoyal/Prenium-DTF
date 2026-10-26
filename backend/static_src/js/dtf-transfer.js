/* One PET sheet and five print motifs. The host owns colour; Hairline owns clocks. */
const {
  Cam, fit, proj, facing, rrect, prism, poly, ringAt, seg,
  mk, pointer, register, disposer, spring, stepS, tween, tset, tval, tdone,
} = HL;

function mount({ stage, svg, read, controlled = false }, value) {
  const bag = disposer(), C = Cam(45, .5, 1.5);
  const edge = rrect(-80,-55,80,55,1.6,12);
  const film = edge.flatMap((a,i)=>{
    const b=edge[(i+1)%edge.length],n=Math.ceil(Math.hypot(b.u-a.u,b.v-a.v)/4);
    return Array.from({length:n},(_,j)=>({...a,u:a.u+(b.u-a.u)*j/n,v:a.v+(b.v-a.v)*j/n}));
  });
  const curl = (u,v) => Math.pow(Math.max(0,(u-54)/26)*Math.max(0,(-v-22)/33),2)*12;
  const corner = [{u:53,v:-55},...film.filter(q=>q.u-q.v>108).sort((a,b)=>a.u+a.v-b.u-b.v),{u:80,v:-28}];
  function normalise(points) {
    const area=points.reduce((a,q,i)=>a+q.u*points[(i+1)%points.length].v-points[(i+1)%points.length].u*q.v,0);
    const ring=area<0?[...points].reverse():points;
    return ring.map((q,i)=>{
      const a=ring[(i+ring.length-1)%ring.length],b=ring[(i+1)%ring.length],n=Math.hypot(b.v-a.v,a.u-b.u)||1;
      return {...q,nu:(b.v-a.v)/n,nv:(a.u-b.u)/n};
    });
  }
  function part(points,colour) {
    const ring=normalise(points),u=ring.reduce((a,q)=>a+q.u,0)/ring.length,v=ring.reduce((a,q)=>a+q.v,0)/ring.length;
    return {ring,inner:ring.map(q=>({...q,u:u+(q.u-u)*.97,v:v+(q.v-v)*.97})),colour};
  }
  function floral(u,v,r) {
    const point=a=>({u:u+r*(.82+.18*Math.cos(8*a))*Math.cos(a),v:v+r*(.82+.18*Math.cos(8*a))*Math.sin(a)});
    const ring=Array.from({length:96},(_,i)=>point(i*Math.PI/48));
    const petals=Array.from({length:8},(_,i)=>part([{u,v},...Array.from({length:13},(_,j)=>point((i-.5)*Math.PI/4+j*Math.PI/48))],i));
    return {parts:[part(ring,0)],marks:petals};
  }
  function ribbon(u,v,w,colour) {
    const edge=Array.from({length:25},(_,i)=>({u:u+w*i/24,v:v+2*Math.sin(i*Math.PI/12)}));
    return part([...edge,...edge.map(q=>({u:q.u,v:q.v+3.5})).reverse()],colour);
  }
  function leaf(u,v,angle,colour) {
    return part(Array.from({length:48},(_,i)=>{
      const a=i*Math.PI/24,x=12*Math.cos(a),y=5*Math.sin(a)*Math.abs(Math.sin(a));
      return {u:u+x*Math.cos(angle)-y*Math.sin(angle),v:v+x*Math.sin(angle)+y*Math.cos(angle)};
    }),colour);
  }
  const sun=part(Array.from({length:49},(_,i)=>({u:35+19*Math.cos(Math.PI+i*Math.PI/48),v:-25+19*Math.sin(Math.PI+i*Math.PI/48)})),5);
  const artworks=[
    floral(-42,-18,24),
    {parts:[sun,ribbon(15,-21,40,7),ribbon(15,-14,40,0),ribbon(15,-7,40,1)]},
    floral(-49,31,11),
    {parts:[part(rrect(-5,22,-2,46,1,4),7),leaf(-9,32,.65,7),leaf(2,22,-.8,0)]},
    {parts:[ribbon(26,15,40,4),ribbon(26,24,40,5),ribbon(26,33,40,1)]},
  ];
  const parts=artworks.flatMap(a=>a.parts), footprint=rrect(-70,-46,68,48,2,8);
  const coverage=parts.map(p=>p.ring.map(q=>[q.u,q.v]));
  fit(C,[...film.map(q=>[q.u,q.v,6+curl(q.u,q.v)]),...parts.flatMap(p=>p.ring.map(q=>[q.u,q.v,100]))],180,170);
  const P=proj(C), front=facing(C), root=mk('g',{},svg);
  const names=['Film PET','Encres 8 couleurs','Blanc optimisé','Poudre adhésive'];
  let maximum=value,active=-1,expanded=false,last='';
  const sx=spring(0),sy=spring(0),layers=[];
  function inside([x,y],points,inset=0){
    let yes=false;
    for(let i=0,j=points.length-1;i<points.length;j=i++){
      const [xi,yi]=points[i],[xj,yj]=points[j];
      if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)yes=!yes;
    }
    if(!yes||!inset)return yes;
    return points.every((a,i)=>{
      const b=points[(i+1)%points.length],du=b[0]-a[0],dv=b[1]-a[1];
      const t=Math.max(0,Math.min(1,((x-a[0])*du+(y-a[1])*dv)/(du*du+dv*dv||1)));
      return Math.hypot(x-a[0]-t*du,y-a[1]-t*dv)>=inset;
    });
  }
  const grains=[];
  for(let row=0;row<45;row++)for(let col=0;col<67;col++){
    const hash=Math.sin(row*127.1+col*311.7)*43758.5453,seed=hash-Math.floor(hash);
    const u=-70+col*2.1+(seed-.5)*1.3,v=-46+row*2.1+(seed-.5)*1.1;
    if(coverage.some(ring=>inside([u,v],ring,.4)))grains.push({u,v,r:.24+seed*.3});
  }
  for(let i=0;i<4;i++){
    const g=mk('g',{class:'dtf-transfer-layer','data-layer':i},root);
    const guide=mk('path',{class:'nf dtf-transfer-guide'},g);
    const outline=mk('path',{class:'sil dtf-layer-outline'},g);
    const crease=mk('path',{class:'nf lo dtf-transfer-crease'},g);
    const rolled=i===0?mk('path',{class:'fo dtf-pet-curl'},g):null;
    const marks=i===1?artworks.flatMap((art,j)=>{
      const group=mk('g',{class:'dtf-sheet-artwork','data-artwork':j},g);
      return (art.marks||art.parts).map(p=>({ring:p.ring,node:mk('path',{class:`dtf-transfer-mark dtf-petal-${p.colour}`},group)}));
    }):[];
    const grain=i===3?mk('path',{class:'nf dtf-powder-grains'},g):null;
    layers[i]={g,guide,outline,crease,rolled,marks,grain,z:tween(6+i*1.2)};
  }
  const connector=mk('path',{class:'nf dtf-transfer-connector'},root);
  function choose(index){
    const open=index>=0;
    if(index===active&&open===expanded)return;
    const from=index<0?Math.max(0,active):index,now=performance.now();
    active=index;expanded=open;
    stage.setAttribute('data-expanded',String(open));stage.setAttribute('data-active-layer',String(index));
    layers.forEach((layer,i)=>{
      tset(layer.z,6+i*(open?maximum:1.2)+(open&&i===index?2:0),now,Math.abs(i-from)*32);
      layer.g.classList.toggle('is-active',i===(index<0?1:index));layer.outline.classList.toggle('hi',i===(index<0?1:index));
    });
    read.textContent=index<0?'rest':names[index];loop.wake();
  }
  function hit(p){
    // Fixed ink silhouettes first; gaps use the nearest fixed layer band.
    for(let i=3;i>=1;i--)if(parts.some(part=>inside(p,ringAt(P,part.ring,6+i*maximum+2))))return i;
    let selected=-1,distance=Infinity;
    for(let i=0;i<4;i++){
      const z=6+i*maximum+2,d=Math.abs(p[1]-P(0,0,z)[1]);
      if(d<distance&&inside(p,ringAt(P,i===0?film:footprint,z))){selected=i;distance=d;}
    }
    return selected;
  }
  const loop=register(stage,(dt,now)=>{
    let moving=stepS(sx,dt)|stepS(sy,dt);
    const signature=[sx.x,sy.x,...layers.map(l=>tval(l.z,now)),active].join(',');
    if(signature!==last){
      root.setAttribute('transform',`translate(${sx.x} ${sy.x})`);
      layers.forEach((layer,i)=>{
        const z=tval(layer.z,now);
        if(i===0){
          layer.outline.setAttribute('d',poly(film.map(q=>P(q.u,q.v,z+curl(q.u,q.v)))));
          layer.crease.setAttribute('d',poly(film.map(q=>P(q.u,q.v,z-.35+curl(q.u,q.v)))));
          layer.rolled.setAttribute('d',poly(corner.map(q=>P(q.u,q.v,z+curl(q.u,q.v)+.02))));
        }else{
          layer.outline.setAttribute('d',parts.map(p=>poly(ringAt(P,p.ring,z+.32))).join(''));
          layer.crease.setAttribute('d',parts.map(p=>prism(P,front,p.ring,p.inner,z,z+.32).crease).join(''));
        }
        layer.guide.setAttribute('d',i>0&&expanded?seg(P(68,0,z),P(68,0,tval(layers[i-1].z,now))):'');
        layer.marks.forEach(mark=>mark.node.setAttribute('d',poly(ringAt(P,mark.ring,z+.4))));
        if(layer.grain)layer.grain.setAttribute('d',grains.map(q=>{
          const [x,y]=P(q.u,q.v,z+.5),r=q.r;
          return `M${x-r},${y}a${r},${r*.65} 0 1 0 ${2*r},0a${r},${r*.65} 0 1 0 ${-2*r},0`;
        }).join(''));
      });
      if(active>=0){
        const a=P(active===0?70:68,0,tval(layers[active].z,now)+.5);
        connector.setAttribute('d',`${seg(a,[300,a[1]])}${seg([300,a[1]],[316,45])}`);
      }else connector.setAttribute('d','');
      last=signature;
    }
    if(layers.some(l=>!tdone(l.z,now)))moving=true;
    return Boolean(moving);
  });
  bag.add(loop.unregister);
  bag.add(pointer(stage,{
    move:p=>{if(stage.getAttribute('data-dismissed')==='true')return;if(!expanded)choose(1);const selected=hit(p);if(selected>=0)choose(selected);sx.t=Math.max(-1.5,Math.min(1.5,(p[0]-200)/100));sy.t=Math.max(-1,Math.min(1,(p[1]-160)/110));loop.wake();},
    down:p=>{const selected=expanded?hit(p):1;choose(selected<0?1:selected);},
    leave:()=>{sx.t=0;sy.t=0;if(!controlled)choose(-1);loop.wake();},
  }));
  bag.add(()=>svg.replaceChildren());
  stage.setAttribute('data-expanded','false');stage.setAttribute('data-active-layer','-1');read.textContent='rest';
  layers[1].g.classList.add('is-active');layers[1].outline.classList.add('hi');loop.wake();
  return {
    set:v=>{maximum=Math.max(20,Math.min(30,v));if(expanded){const i=active;active=-1;choose(i);}},
    select:choose,collapse:()=>choose(-1),destroy:bag.dispose,
  };
}

hairline({
  name:'dtf-transfer',
  means:'Une planche de cinq motifs sur film PET au coin courbé : les couches se séparent au survol et se réassemblent au départ.',
  rules:[1,2,3,7,8,9],range:[22,26,30],
  tour:[[180,217],[180,163],[180,109],null],mount,
});

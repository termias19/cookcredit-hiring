// ============================================================
// REWARD SIGNAL DENSITY (THESIS HERO)
// ============================================================
(function(){
var rc=document.getElementById('rc');
if(!rc)return;
var rx=rc.getContext('2d');
var RW=rc.offsetWidth,RH=280;
rc.width=RW*2;rc.height=RH*2;rx.scale(2,2);
var BG0='#1a1816';
var GRID0='rgba(255,255,255,0.03)';
var AX0='#3a3630';
var DOT_LAB='rgba(127,119,221,0.6)';
var DOT_CC='rgba(29,158,117,0.7)';
var TXT0='#6a6560';

var labDots=[];
for(var i=0;i<8;i++){labDots.push({x:0.05+Math.random()*0.38,y:0.85+Math.random()*0.1,r:2+Math.random()*2,phase:Math.random()*Math.PI*2});}
labDots.push({x:0.42,y:0.15,r:5,phase:0});

var ccDots=[];
for(var i2=0;i2<120;i2++){ccDots.push({x:0.55+Math.random()*0.40,y:0.1+Math.random()*0.8,r:1.5+Math.random()*2.5,phase:Math.random()*Math.PI*2,delay:i2*0.02});}

var frame0=0;
function draw0(){
  frame0++;
  var t=frame0/60;
  rx.fillStyle=BG0;rx.fillRect(0,0,RW,RH);
  rx.strokeStyle=GRID0;rx.lineWidth=0.5;
  for(var x=0;x<RW;x+=40){rx.beginPath();rx.moveTo(x,0);rx.lineTo(x,RH);rx.stroke();}
  for(var y=0;y<RH;y+=40){rx.beginPath();rx.moveTo(0,y);rx.lineTo(RW,y);rx.stroke();}
  rx.strokeStyle=AX0;rx.lineWidth=0.5;
  rx.beginPath();rx.moveTo(RW*0.5,10);rx.lineTo(RW*0.5,RH-10);rx.stroke();
  rx.font='500 10px monospace';rx.fillStyle=TXT0;
  rx.fillText('scripted lab demo',RW*0.12,RH-8);
  rx.fillText('in-situ cooking session',RW*0.62,RH-8);
  rx.save();rx.translate(8,RH*0.5);rx.rotate(-Math.PI/2);
  rx.fillText('reward density',0,0);rx.restore();
  rx.font='9px monospace';rx.fillStyle=TXT0;
  rx.fillText('terminal reward only',RW*0.15,26);
  rx.fillText('per-stroke + per-pause + terminal',RW*0.55,26);
  var appear=Math.min(t*0.5,1);
  labDots.forEach(function(d,i){
    var a=Math.min(appear,1)*0.6;
    if(i===labDots.length-1){
      var pulse=0.7+0.3*Math.sin(t*2+d.phase);
      rx.globalAlpha=a*pulse;rx.fillStyle=DOT_LAB;
      rx.beginPath();rx.arc(d.x*RW,d.y*RH,d.r*2,0,Math.PI*2);rx.fill();
      rx.globalAlpha=a;rx.strokeStyle='rgba(127,119,221,0.3)';rx.lineWidth=0.5;
      rx.beginPath();rx.arc(d.x*RW,d.y*RH,d.r*4,0,Math.PI*2);rx.stroke();
    } else {
      rx.globalAlpha=a*0.3;rx.fillStyle=DOT_LAB;
      rx.beginPath();rx.arc(d.x*RW,d.y*RH,d.r,0,Math.PI*2);rx.fill();
    }
  });
  rx.globalAlpha=1;
  ccDots.forEach(function(d){
    var a2=Math.max(0,Math.min((t-d.delay)*2,1));
    if(a2<=0)return;
    var pulse=0.6+0.4*Math.sin(t*1.5+d.phase);
    rx.globalAlpha=a2*pulse;rx.fillStyle=DOT_CC;
    rx.beginPath();rx.arc(d.x*RW,d.y*RH,d.r,0,Math.PI*2);rx.fill();
  });
  rx.globalAlpha=1;
  if(t>1){
    var countA=Math.min(Math.floor((t-1)*3),120);
    rx.font='500 12px monospace';
    rx.fillStyle=DOT_CC;rx.fillText(countA+' reward signals',RW*0.62,RH*0.5);
    rx.fillStyle=DOT_LAB;rx.fillText('1 reward signal',RW*0.12,RH*0.5);
  }
  if(t>3){
    rx.font='10px monospace';rx.fillStyle=TXT0;
    rx.fillText('density ratio: '+Math.min(Math.floor((t-3)*10),120)+':1',RW*0.62,RH*0.5+18);
  }
  requestAnimationFrame(draw0);
}
draw0();
})();


// ============================================================
// HAND POSE & BLADE PREDICTION
// ============================================================
(function(){
const cv=document.getElementById('cv'),ctx=cv.getContext('2d');
const W=cv.offsetWidth,H=420;
cv.width=W*2;cv.height=H*2;ctx.scale(2,2);
const BG='#1a1816';
const BONE='#1D9E75';const JOINT='#5DCAA5';const BLADE='#D85A30';
const PREDICT='#378ADD';const TRAIL='rgba(55,138,221,0.15)';
const TXT='#e0ddd6';const TXTS='#6a6560';
const BOARD_C='#2a2622';const BOARD_B='#3a3630';

const handBase=[
[0.50,0.55],[0.44,0.52],[0.40,0.46],[0.37,0.40],[0.34,0.35],
[0.43,0.38],[0.41,0.30],[0.40,0.24],[0.39,0.19],
[0.48,0.36],[0.48,0.27],[0.48,0.21],[0.48,0.16],
[0.53,0.38],[0.55,0.30],[0.56,0.24],[0.56,0.19],
[0.57,0.42],[0.60,0.37],[0.62,0.33],[0.63,0.29]
];
const bones=[[0,1],[1,2],[2,3],[3,4],[0,5],[5,6],[6,7],[7,8],[5,9],[9,10],[10,11],[11,12],[9,13],[13,14],[14,15],[15,16],[13,17],[17,18],[18,19],[19,20],[0,17]];
var t=0,strokes=0,lastStrokeT=0,bladeTrail=[];

function getHand(time){
  var chop=Math.sin(time*3.5)*0.04;
  var sway=Math.sin(time*1.2)*0.015;
  return handBase.map(function(p,i){
    var dy=chop*(1-i*0.02);
    var dx=sway;
    if(i>=5&&i<=8)dy+=Math.sin(time*4+i)*0.008;
    if(i>=9&&i<=12)dy+=Math.sin(time*4.2+i)*0.006;
    return[p[0]+dx,p[1]+dy];
  });
}

function drawBoard(w,h){
  var bx=w*0.15,by=h*0.35,bw=w*0.7,bh=h*0.55,r=8;
  ctx.fillStyle=BOARD_C;ctx.strokeStyle=BOARD_B;ctx.lineWidth=1.5;
  ctx.beginPath();
  ctx.moveTo(bx+r,by);ctx.lineTo(bx+bw-r,by);ctx.quadraticCurveTo(bx+bw,by,bx+bw,by+r);
  ctx.lineTo(bx+bw,by+bh-r);ctx.quadraticCurveTo(bx+bw,by+bh,bx+bw-r,by+bh);
  ctx.lineTo(bx+r,by+bh);ctx.quadraticCurveTo(bx,by+bh,bx,by+bh-r);
  ctx.lineTo(bx,by+r);ctx.quadraticCurveTo(bx,by,bx+r,by);
  ctx.closePath();ctx.fill();ctx.stroke();
  ctx.font='11px monospace';ctx.fillStyle=TXTS;
  ctx.fillText('cutting surface',bx+bw/2-40,by+bh-12);
}

function drawOnionPieces(w,h){
  var cx=w*0.45,cy=h*0.62;
  ctx.globalAlpha=0.6;
  for(var i=0;i<Math.min(strokes*2,16);i++){
    var px=cx+Math.sin(i*2.1)*30+Math.cos(i*1.3)*15;
    var py=cy+Math.cos(i*1.7)*20+Math.sin(i*0.9)*10;
    var sz=4+Math.random()*3;
    ctx.fillStyle='#8a4a6a';
    ctx.beginPath();ctx.ellipse(px,py,sz,sz*0.7,i*0.5,0,Math.PI*2);ctx.fill();
  }
  ctx.globalAlpha=1;
}

function drawHand(pts,w,h){
  bones.forEach(function(b){
    ctx.strokeStyle=BONE;ctx.lineWidth=2;ctx.beginPath();
    ctx.moveTo(pts[b[0]][0]*w,pts[b[0]][1]*h);
    ctx.lineTo(pts[b[1]][0]*w,pts[b[1]][1]*h);ctx.stroke();
  });
  pts.forEach(function(p,i){
    ctx.fillStyle=i===0?BLADE:JOINT;
    ctx.beginPath();ctx.arc(p[0]*w,p[1]*h,i===0?6:3.5,0,Math.PI*2);ctx.fill();
    if(i===0){ctx.strokeStyle=BONE;ctx.lineWidth=1;ctx.beginPath();ctx.arc(p[0]*w,p[1]*h,10,0,Math.PI*2);ctx.stroke();}
  });
}

function drawBladePrediction(pts,w,h,time){
  var wx=pts[0][0]*w,wy=pts[0][1]*h;
  var mx=pts[9][0]*w,my=pts[9][1]*h;
  var axis=Math.atan2(my-wy,mx-wx);
  var absAng=axis+(-0.3);
  var bx=wx+180*Math.cos(absAng),by=wy+180*Math.sin(absAng);
  bladeTrail.push({x:bx,y:by});if(bladeTrail.length>60)bladeTrail.shift();
  if(bladeTrail.length>1){ctx.strokeStyle=TRAIL;ctx.lineWidth=2;ctx.beginPath();bladeTrail.forEach(function(p,i){if(i===0)ctx.moveTo(p.x,p.y);else ctx.lineTo(p.x,p.y);});ctx.stroke();}
  ctx.setLineDash([4,4]);ctx.strokeStyle=PREDICT;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(wx,wy);ctx.lineTo(bx,by);ctx.stroke();ctx.setLineDash([]);
  ctx.fillStyle=PREDICT;ctx.beginPath();ctx.arc(bx,by,5,0,Math.PI*2);ctx.fill();
  ctx.strokeStyle=PREDICT;ctx.lineWidth=1;ctx.beginPath();ctx.arc(bx,by,12,0,Math.PI*2);ctx.stroke();
  var bladeAng=axis-0.2;
  ctx.strokeStyle=BLADE;ctx.lineWidth=2.5;ctx.lineCap='round';ctx.beginPath();
  ctx.moveTo(bx-21*Math.cos(bladeAng),by-21*Math.sin(bladeAng));
  ctx.lineTo(bx+49*Math.cos(bladeAng),by+49*Math.sin(bladeAng));ctx.stroke();ctx.lineCap='butt';
  ctx.font='500 11px monospace';ctx.fillStyle=BONE;ctx.fillText('WRIST [0]',wx+14,wy-4);
  ctx.fillStyle=PREDICT;ctx.fillText('blade (predicted)',bx+16,by-4);
  ctx.fillStyle=TXTS;ctx.font='10px monospace';
  ctx.fillText('SE(2): θ='+(axis*180/Math.PI).toFixed(1)+'°  d=180px  α=-17.2°',wx+14,wy+14);
}

function drawStrokeSignal(w,h,time){
  var sx2=w*0.04,sy2=h*0.05,sw=w*0.25,sh=50;
  ctx.fillStyle='rgba(26,24,22,0.9)';ctx.fillRect(sx2,sy2,sw,sh);
  ctx.strokeStyle='#3a3630';ctx.lineWidth=0.5;ctx.strokeRect(sx2,sy2,sw,sh);
  ctx.font='10px monospace';ctx.fillStyle=TXTS;ctx.fillText('wrist_y signal',sx2+4,sy2+12);
  ctx.strokeStyle=BONE;ctx.lineWidth=1.2;ctx.beginPath();
  for(var i=0;i<60;i++){var x=sx2+4+i*(sw-8)/60;var v=sy2+sh/2+Math.sin((time-60+i)*3.5/60*Math.PI*2)*15;if(i===0)ctx.moveTo(x,v);else ctx.lineTo(x,v);}
  ctx.stroke();
}

function drawHUD(w,h,time){
  ctx.fillStyle='rgba(26,24,22,0.9)';ctx.fillRect(w-210,8,202,20);
  ctx.font='10px monospace';ctx.fillStyle=TXTS;
  ctx.fillText('f='+Math.floor(time*59.5)+'  t='+time.toFixed(2)+'s  landmarks=42  conf=0.99',w-206,22);
}

function draw1(){
  t+=1/60;
  ctx.fillStyle=BG;ctx.fillRect(0,0,W,H);
  drawBoard(W,H);drawOnionPieces(W,H);
  var pts=getHand(t);
  drawBladePrediction(pts,W,H,t);drawHand(pts,W,H);
  drawStrokeSignal(W,H,t);drawHUD(W,H,t);
  var v=Math.sin(t*3.5);if(v>0.95&&t-lastStrokeT>0.5){strokes++;lastStrokeT=t;}
  var phase=Math.floor(t/2)%5;
  ['t-hpe','t-se2','t-ema','t-kpd','t-iou'].forEach(function(id,i){var el=document.getElementById(id);if(el)el.className=i<=phase?'term active':'term';});
  document.getElementById('s-kp').textContent='42';
  document.getElementById('s-conf').textContent='99%';
  document.getElementById('s-str').textContent=strokes;
  document.getElementById('s-hz').textContent=strokes>1?(strokes/(t+0.01)).toFixed(1):'0.0';
  requestAnimationFrame(draw1);
}
draw1();
})();


// ============================================================
// PIECE SEGMENTATION
// ============================================================
(function(){
var pc=document.getElementById('pc'),px=pc.getContext('2d');
var PW=pc.offsetWidth,PH=380;
pc.width=PW*2;pc.height=PH*2;px.scale(2,2);
var BG2='#1a1816';
var phases2=['absdiff(frame, piece_bg)','morphological open/close','findContours','watershed split','distance transform','area measurement'];
var pbar=document.getElementById('pbar'),plbls=document.getElementById('plbls');
phases2.forEach(function(p,i){
  var s=document.createElement('div');s.className='phase-seg';s.id='ps2-'+i;pbar.appendChild(s);
  var l=document.createElement('div');l.className='phase-lbl';l.textContent=p;l.id='pl2-'+i;plbls.appendChild(l);
});
var COLORS=['#8a4a6a','#7a5a7a','#9a3a5a','#6a4a8a','#aa4a5a','#7a6a5a','#8a5a4a','#6a5a6a','#9a5a6a','#7a4a7a','#8a6a5a','#9a4a7a','#6a6a7a','#8a3a7a','#7a5a6a'];
var pieces=[];
function initPieces(){
  pieces.length=0;var cx=PW*0.5,cy=PH*0.45;
  for(var i=0;i<15;i++){
    var ang=i*0.43+Math.sin(i)*0.3,r=30+Math.random()*60;
    var x=cx+Math.cos(ang)*r-20+Math.random()*40,y=cy+Math.sin(ang)*r-20+Math.random()*30;
    var w=12+Math.random()*18,h=10+Math.random()*14,rot=Math.random()*Math.PI;
    var verts=[],nv=6+Math.floor(Math.random()*5);
    for(var j=0;j<nv;j++){var a=j/nv*Math.PI*2,rr=1+Math.random()*0.3;verts.push({x:Math.cos(a)*w*0.5*rr,y:Math.sin(a)*h*0.5*rr});}
    pieces.push({x:x,y:y,w:w,h:h,rot:rot,verts:verts,color:COLORS[i%COLORS.length],distVal:Math.random()*4+2,areaVal:Math.round(w*h*0.78*0.11+Math.random()*20+50)});
  }
}
initPieces();
var frame2=0;var PHASE_DUR=90;var TOTAL=phases2.length*PHASE_DUR;
function drawBoardBg(){
  px.fillStyle='#2a2622';var r2=8,bx=PW*0.08,by=PH*0.08,bw=PW*0.84,bh=PH*0.78;
  px.beginPath();px.moveTo(bx+r2,by);px.lineTo(bx+bw-r2,by);px.quadraticCurveTo(bx+bw,by,bx+bw,by+r2);
  px.lineTo(bx+bw,by+bh-r2);px.quadraticCurveTo(bx+bw,by+bh,bx+bw-r2,by+bh);
  px.lineTo(bx+r2,by+bh);px.quadraticCurveTo(bx,by+bh,bx,by+bh-r2);
  px.lineTo(bx,by+r2);px.quadraticCurveTo(bx,by,bx+r2,by);px.closePath();px.fill();
}
function drawPiece(p,phase,phaseT){
  px.save();px.translate(p.x,p.y);px.rotate(p.rot);
  if(phase>=0){px.globalAlpha=Math.min(phase===0?phaseT/30:1,1)*0.7;px.fillStyle=p.color;px.beginPath();p.verts.forEach(function(v,i){if(i===0)px.moveTo(v.x,v.y);else px.lineTo(v.x,v.y);});px.closePath();px.fill();px.globalAlpha=1;}
  if(phase>=2){var ca=phase===2?Math.min(phaseT/20,1):1;px.strokeStyle='rgba(29,158,117,'+ca+')';px.lineWidth=1.5;px.beginPath();p.verts.forEach(function(v,i){if(i===0)px.moveTo(v.x,v.y);else px.lineTo(v.x,v.y);});px.closePath();px.stroke();}
  if(phase>=3){var wa=phase===3?Math.min(phaseT/25,1):1;px.fillStyle='rgba(55,138,221,'+wa*0.3+')';px.beginPath();px.arc(0,0,p.distVal,0,Math.PI*2);px.fill();px.fillStyle='rgba(55,138,221,'+wa+')';px.beginPath();px.arc(0,0,2,0,Math.PI*2);px.fill();}
  if(phase>=4){var da=phase===4?Math.min(phaseT/30,1):1;for(var r=1;r<=3;r++){px.strokeStyle='rgba(216,90,48,'+da*0.15*(4-r)+')';px.lineWidth=1;px.beginPath();px.arc(0,0,p.distVal*r*1.5,0,Math.PI*2);px.stroke();}}
  if(phase>=5){var ma=phase===5?Math.min(phaseT/20,1):1;px.fillStyle='rgba(224,221,214,'+ma*0.9+')';px.font='500 9px monospace';px.fillText(p.areaVal+'mm2',p.w*0.3,-p.h*0.1);}
  px.restore();
}
function drawGrid2(){px.strokeStyle='rgba(255,255,255,0.03)';px.lineWidth=0.5;for(var x=0;x<PW;x+=20){px.beginPath();px.moveTo(x,0);px.lineTo(x,PH);px.stroke();}for(var y=0;y<PH;y+=20){px.beginPath();px.moveTo(0,y);px.lineTo(PW,y);px.stroke();}}
function drawPhaseLabel(phase,phaseT){
  var labels=['background subtraction','morphological filtering','contour extraction','watershed segmentation','distance transform','geometric measurement'];
  var subs=['absdiff(frame_t, piece_bg) > 25','MORPH_OPEN(3x3) then MORPH_CLOSE(5x5)','RETR_EXTERNAL + CHAIN_APPROX_SIMPLE','markers from local maxima of dist transform','L2 norm, cv::distanceTransform','area = contourArea(c), solidity = area/hull'];
  px.fillStyle='rgba(26,24,22,0.92)';var bw2=320,bh2=42,bx2=PW-bw2-16,by2=16;
  px.fillRect(bx2,by2,bw2,bh2);px.strokeStyle='#3a3630';px.lineWidth=0.5;px.strokeRect(bx2,by2,bw2,bh2);
  px.font='500 12px monospace';px.fillStyle='#1D9E75';px.fillText(labels[phase],bx2+10,by2+16);
  px.font='10px monospace';px.fillStyle='#6a6560';px.fillText(subs[phase],bx2+10,by2+32);
}
function drawMorphKernel(phase,phaseT){
  if(phase!==1)return;var alpha=Math.min(phaseT/20,1),kx=PW*0.08+10,ky=PH*0.08+10;
  px.globalAlpha=alpha;px.strokeStyle='#D85A30';px.lineWidth=1;
  var ksz=phaseT<45?3:5,label=phaseT<45?'OPEN 3x3':'CLOSE 5x5';
  for(var r=0;r<ksz;r++)for(var c=0;c<ksz;c++){px.strokeRect(kx+c*8,ky+r*8,7,7);px.fillStyle='rgba(216,90,48,0.2)';px.fillRect(kx+c*8+1,ky+r*8+1,5,5);}
  px.font='9px monospace';px.fillStyle='#D85A30';px.fillText(label,kx,ky+ksz*8+12);px.globalAlpha=1;
}
function anim2(){
  frame2=(frame2+1)%(TOTAL+120);if(frame2>=TOTAL)frame2=0;
  var cp=Math.min(Math.floor(frame2/PHASE_DUR),phases2.length-1),pt=frame2-cp*PHASE_DUR;
  px.fillStyle=BG2;px.fillRect(0,0,PW,PH);drawGrid2();drawBoardBg();
  pieces.forEach(function(p){drawPiece(p,cp,pt);});drawPhaseLabel(cp,pt);drawMorphKernel(cp,pt);
  for(var i=0;i<phases2.length;i++){document.getElementById('ps2-'+i).className=i<=cp?'phase-seg on':'phase-seg';document.getElementById('pl2-'+i).className=i<=cp?'phase-lbl on':'phase-lbl';}
  document.getElementById('mv-n').textContent=cp>=2?'15':'--';
  document.getElementById('mv-med').textContent=cp>=5?'73.7':'--';
  document.getElementById('mv-cv').textContent=cp>=5?'0.142':'--';
  document.getElementById('mc-n').className=cp>=2?'metric-card highlight':'metric-card';
  document.getElementById('mc-med').className=cp>=5?'metric-card highlight':'metric-card';
  document.getElementById('mc-cv').className=cp>=5?'metric-card highlight':'metric-card';
  requestAnimationFrame(anim2);
}
anim2();
})();


// ============================================================
// SCORING RUBRIC
// ============================================================
(function(){
var sc=document.getElementById('sc'),sx=sc.getContext('2d');
var SW=sc.offsetWidth,SH=320;
sc.width=SW*2;sc.height=SH*2;sx.scale(2,2);
var BG3='#1a1816';var GRN='#1D9E75';var BLU='#378ADD';var ORA='#D85A30';
var TXT3='#e0ddd6';var TXTS3='#6a6560';var k=1.25,c=1.8,t3=0;

function scoreFineness(obs){if(obs<=0)return 0;return 100*Math.exp(-k*Math.abs(Math.log(obs/100)));}
function scoreConsistency(cv){return 100*Math.exp(-c*Math.max(0,cv));}
function easeInOut(t){return t<0.5?2*t*t:1-Math.pow(-2*t+2,2)/2;}

function drawCurve(x0,y0,w,h,fn,xLabel,yLabel,curX,color,title,paramStr){
  sx.strokeStyle='rgba(255,255,255,0.04)';sx.lineWidth=0.5;
  for(var i=0;i<=4;i++){var yy=y0+i*h/4;sx.beginPath();sx.moveTo(x0,yy);sx.lineTo(x0+w,yy);sx.stroke();}
  for(var i2=0;i2<=4;i2++){var xx=x0+i2*w/4;sx.beginPath();sx.moveTo(xx,y0);sx.lineTo(xx,y0+h);sx.stroke();}
  sx.strokeStyle='#3a3630';sx.lineWidth=0.5;sx.strokeRect(x0,y0,w,h);
  sx.font='500 11px monospace';sx.fillStyle=TXT3;sx.fillText(title,x0,y0-8);
  sx.font='9px monospace';sx.fillStyle=TXTS3;
  var xlw=sx.measureText(xLabel).width;
  sx.fillText(xLabel,x0+w/2-xlw/2,y0+h+14);
  sx.save();sx.translate(x0-10,y0+h/2);sx.rotate(-Math.PI/2);sx.fillText(yLabel,-15,0);sx.restore();
  sx.strokeStyle=color;sx.lineWidth=2;sx.beginPath();
  for(var j=0;j<=100;j++){var xv=j/100,yv=fn(xv)/100,px2=x0+xv*w,py2=y0+h-yv*h;if(j===0)sx.moveTo(px2,py2);else sx.lineTo(px2,py2);}
  sx.stroke();
  if(curX>=0&&curX<=1){
    var cxp=x0+curX*w,cyp=y0+h-(fn(curX)/100)*h;
    sx.setLineDash([3,3]);sx.strokeStyle=TXTS3;sx.lineWidth=0.5;
    sx.beginPath();sx.moveTo(cxp,y0+h);sx.lineTo(cxp,cyp);sx.stroke();
    sx.beginPath();sx.moveTo(x0,cyp);sx.lineTo(cxp,cyp);sx.stroke();sx.setLineDash([]);
    sx.fillStyle=color;sx.beginPath();sx.arc(cxp,cyp,4,0,Math.PI*2);sx.fill();
    sx.fillStyle='rgba(26,24,22,0.8)';sx.beginPath();sx.arc(cxp,cyp,2,0,Math.PI*2);sx.fill();
    sx.font='500 10px monospace';sx.fillStyle=color;sx.fillText(Math.round(fn(curX)),cxp+8,cyp-6);
  }
  sx.font='9px monospace';sx.fillStyle=TXTS3;sx.fillText('0',x0-12,y0+h+4);sx.fillText('100',x0-24,y0+6);
}

function anim3(){
  t3=(t3+1)%600;var progress=t3/600,ep=easeInOut(Math.min(progress*2,1));
  sx.fillStyle=BG3;sx.fillRect(0,0,SW,SH);
  var simArea=40+ep*120,simCV=0.05+ep*0.45;
  var normArea=simArea/200,normCV=simCV/0.5;
  var finFn=function(x){var obs=x*200;if(obs<=0)return 0;return 100*Math.exp(-k*Math.abs(Math.log(obs/100)));};
  var conFn=function(x){return 100*Math.exp(-c*(x*0.5));};
  var pad=24,cw=(SW-pad*4)/3,ch=SH-90;
  drawCurve(pad,40,cw,ch,finFn,'obs / tgt','score',normArea,ORA,'fineness','S = 100*exp(-k*|ln(obs/tgt)|)');
  var conScore=scoreConsistency(simCV);
  drawCurve(pad*2+cw,40,cw,ch,conFn,'CV','score',normCV,BLU,'consistency','S = 100*exp(-c*CV)');
  var qualityGate=Math.min(1,(conScore/100)*0.85);
  var spdGated=function(x){var hz=x*5;return Math.min(100,100*(hz-1)/3)*qualityGate;};
  drawCurve(pad*3+cw*2,40,cw,ch,spdGated,'cadence (Hz)','score',ep,GRN,'speed (gated)','S_spd * clamp(C/100 * conf)');
  if(qualityGate<0.7){sx.font='9px monospace';sx.fillStyle=ORA;sx.fillText('quality gate: '+qualityGate.toFixed(2),pad*3+cw*2,40+ch+28);}
  var fin=scoreFineness(simArea),con=conScore,spd=spdGated(ep),raw=0.35*fin+0.45*con+0.20*spd;
  if(progress>0.1){
    document.getElementById('sv-fin').textContent=Math.round(fin);
    document.getElementById('sv-con').textContent=Math.round(con);
    document.getElementById('sv-spd').textContent=Math.round(spd);
    document.getElementById('sv-raw').textContent=Math.round(raw);
    document.getElementById('ss-fin').textContent='obs='+Math.round(simArea)+'mm2 tgt=100';
    document.getElementById('ss-con').textContent='CV='+simCV.toFixed(2);
    document.getElementById('ss-spd').textContent='gate='+qualityGate.toFixed(2);
    ['cell-fin','cell-con','cell-spd','cell-raw'].forEach(function(id,i){document.getElementById(id).className=progress>0.15+i*0.15?'score-cell pulse':'score-cell';});
    document.getElementById('f-text').textContent='raw = 0.35('+Math.round(fin)+') + 0.45('+Math.round(con)+') + 0.20('+Math.round(spd)+') = '+Math.round(raw);
    if(progress>0.8){
      var pass=raw>=70;var fb=document.getElementById('f-badge');
      fb.style.opacity='1';fb.textContent=pass?'PASS':'FAIL';
      fb.style.background=pass?'#0a2e22':'#2e0a0a';fb.style.color=pass?'#1D9E75':'#A32D2D';
      document.getElementById('fstrip').className='formula-strip active';
    }
  }
  requestAnimationFrame(anim3);
}
anim3();
})();


// ============================================================
// DATA PIPELINE + TRAINING FLYWHEEL
// ============================================================
(function(){
var dp=document.getElementById('dp'),dx=dp.getContext('2d');
var DW=dp.offsetWidth,DH=400;
dp.width=DW*2;dp.height=DH*2;dx.scale(2,2);
var BG4='#1a1816';
var GRN2='#1D9E75';var BLU2='#378ADD';var ORA2='#D85A30';var PUR='#7F77DD';var TEAL='#5DCAA5';
var TXT4='#e0ddd6';var TXTS4='#6a6560';

var stages=[
  {x:0.08,y:0.15,w:0.14,h:0.18,label:'phone',sub:'60fps',color:GRN2},
  {x:0.27,y:0.15,w:0.14,h:0.18,label:'on-device',sub:'MediaPipe',color:TEAL},
  {x:0.46,y:0.15,w:0.14,h:0.18,label:'protobuf',sub:'session.pb',color:BLU2},
  {x:0.65,y:0.15,w:0.14,h:0.18,label:'cloud run',sub:'zarr',color:ORA2},
  {x:0.84,y:0.15,w:0.14,h:0.18,label:'GCS',sub:'episodes',color:PUR},
];
var bottomStages=[
  {x:0.84,y:0.58,w:0.14,h:0.18,label:'CookDB',sub:'Postgres',color:PUR},
  {x:0.60,y:0.58,w:0.18,h:0.18,label:'training',sub:'PyTorch',color:ORA2},
  {x:0.34,y:0.58,w:0.18,h:0.18,label:'eval',sub:'mAP / r',color:BLU2},
  {x:0.08,y:0.58,w:0.18,h:0.18,label:'deploy',sub:'OTA update',color:GRN2},
];
var frame4=0;var particles=[];

function spawnP(sx2,sy2,ex,ey,color,delay){particles.push({sx:sx2,sy:sy2,ex:ex,ey:ey,color:color,t:0,delay:delay,speed:0.008+Math.random()*0.005,alive:true});}

function drawBox(s,phase,activeIdx){
  var x=s.x*DW,y=s.y*DH,w=s.w*DW,h=s.h*DH,active=phase>=activeIdx,r=6;
  dx.fillStyle=active?'rgba(30,28,24,0.95)':'rgba(26,24,22,0.5)';
  dx.strokeStyle=active?s.color:'#3a3630';dx.lineWidth=active?1.5:0.5;
  dx.beginPath();dx.moveTo(x+r,y);dx.lineTo(x+w-r,y);dx.quadraticCurveTo(x+w,y,x+w,y+r);
  dx.lineTo(x+w,y+h-r);dx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);
  dx.lineTo(x+r,y+h);dx.quadraticCurveTo(x,y+h,x,y+h-r);dx.lineTo(x,y+r);dx.quadraticCurveTo(x,y,x+r,y);
  dx.closePath();dx.fill();dx.stroke();
  if(active){dx.fillStyle=s.color;dx.beginPath();dx.arc(x+12,y+12,3,0,Math.PI*2);dx.fill();}
  dx.font='500 11px monospace';dx.fillStyle=active?TXT4:TXTS4;dx.fillText(s.label,x+10,y+h/2-2);
  dx.font='9px monospace';dx.fillStyle=TXTS4;dx.fillText(s.sub,x+10,y+h/2+12);
}

function drawArrow(x1,y1,x2,y2,color,active){
  dx.strokeStyle=active?color:TXTS4;dx.lineWidth=active?1.5:0.5;
  dx.setLineDash(active?[]:[4,4]);dx.beginPath();dx.moveTo(x1,y1);dx.lineTo(x2,y2);dx.stroke();dx.setLineDash([]);
  if(active){var ang=Math.atan2(y2-y1,x2-x1);dx.fillStyle=color;dx.beginPath();dx.moveTo(x2,y2);dx.lineTo(x2-8*Math.cos(ang-0.4),y2-8*Math.sin(ang-0.4));dx.lineTo(x2-8*Math.cos(ang+0.4),y2-8*Math.sin(ang+0.4));dx.closePath();dx.fill();}
}

function drawParticles(){
  particles.forEach(function(p){if(!p.alive)return;if(p.delay>0){p.delay--;return;}p.t+=p.speed;if(p.t>=1){p.alive=false;return;}
  var x=p.sx+(p.ex-p.sx)*p.t,y=p.sy+(p.ey-p.sy)*p.t+Math.sin(p.t*Math.PI*3)*4;
  dx.globalAlpha=1-p.t*0.5;dx.fillStyle=p.color;dx.beginPath();dx.arc(x,y,2.5,0,Math.PI*2);dx.fill();dx.globalAlpha=1;});
  for(var i=particles.length-1;i>=0;i--)if(!particles[i].alive)particles.splice(i,1);
}

function drawFlywheel(phase){
  if(phase<6)return;var cx=DW*0.5,cy=DH*0.48,rx=DW*0.38,ry=30;
  dx.strokeStyle=GRN2;dx.lineWidth=1;dx.globalAlpha=0.3;dx.setLineDash([4,6]);
  dx.beginPath();dx.ellipse(cx,cy,rx,ry,0,0,Math.PI*2);dx.stroke();dx.setLineDash([]);dx.globalAlpha=1;
  var fAng=(frame4*0.015)%(Math.PI*2),fx=cx+rx*Math.cos(fAng),fy=cy+ry*Math.sin(fAng);
  dx.fillStyle=GRN2;dx.beginPath();dx.arc(fx,fy,4,0,Math.PI*2);dx.fill();
}

function drawDataLabels(phase){
  if(phase<2)return;
  var labels=['hand/landmarks_left (T,21,3)','blade/predicted_center (T,2)','strokes/timestamps (N,)','pieces/snapshots/0/areas_px','score/raw_score'];
  dx.font='9px monospace';
  labels.forEach(function(l,i){var alpha=Math.min(1,Math.max(0,(phase-2-i*0.3)*2));if(alpha<=0)return;dx.globalAlpha=alpha*0.7;dx.fillStyle=TXTS4;dx.fillText(l,DW*0.30,DH*0.38+i*14);});
  dx.globalAlpha=1;
}

var flyMsgs=['initializing capture pipeline...','MediaPipe hand_landmarker_v2 loaded','on-device inference: 5ms / frame','serializing session to protobuf','uploading to gs://cookcredit-raw/','processing worker: zarr conversion','INSERT INTO episodes (episode_hash, task, ...)','SQL: SELECT * WHERE task=\'onion_small_dice\' AND active','training: piece_seg_v2, epoch 12/50, loss=0.342','eval: mAP50 = 0.587 (+0.247 from v1)','deploying piece_seg_v2.tflite to app','flywheel: more sessions > better models > better scores'];

function anim4(){
  frame4++;var cycle=900,t2=frame4%cycle,phase=Math.min(Math.floor(t2/75),11);
  dx.fillStyle=BG4;dx.fillRect(0,0,DW,DH);
  dx.strokeStyle='rgba(255,255,255,0.025)';dx.lineWidth=0.5;
  for(var x=0;x<DW;x+=30){dx.beginPath();dx.moveTo(x,0);dx.lineTo(x,DH);dx.stroke();}
  for(var y=0;y<DH;y+=30){dx.beginPath();dx.moveTo(0,y);dx.lineTo(DW,y);dx.stroke();}
  stages.forEach(function(s,i){drawBox(s,phase,i);});
  bottomStages.forEach(function(s,i){drawBox(s,phase,i+5);});
  for(var i2=0;i2<stages.length-1;i2++){var a=stages[i2],b=stages[i2+1];drawArrow((a.x+a.w)*DW,(a.y+a.h/2)*DH,b.x*DW,(b.y+b.h/2)*DH,a.color,phase>i2);}
  drawArrow((stages[4].x+stages[4].w/2)*DW,(stages[4].y+stages[4].h)*DH,(bottomStages[0].x+bottomStages[0].w/2)*DW,bottomStages[0].y*DH,PUR,phase>=5);
  for(var i3=0;i3<bottomStages.length-1;i3++){var a2=bottomStages[i3],b2=bottomStages[i3+1];drawArrow(a2.x*DW,(a2.y+a2.h/2)*DH,(b2.x+b2.w)*DW,(b2.y+b2.h/2)*DH,a2.color,phase>i3+5);}
  drawArrow(bottomStages[3].x*DW,bottomStages[3].y*DH,(stages[0].x+stages[0].w/2)*DW,(stages[0].y+stages[0].h)*DH,GRN2,phase>=9);
  if(frame4%12===0&&phase<10){var idx=Math.min(phase,stages.length-2);if(idx<stages.length-1){var aa=stages[idx],bb=stages[idx+1];spawnP((aa.x+aa.w)*DW,(aa.y+aa.h/2)*DH,bb.x*DW,(bb.y+bb.h/2)*DH,aa.color,0);}}
  if(frame4%18===0&&phase>=5&&phase<9){var bi=Math.min(phase-5,bottomStages.length-2);if(bi<bottomStages.length-1){var aa2=bottomStages[bi],bb2=bottomStages[bi+1];spawnP(aa2.x*DW,(aa2.y+aa2.h/2)*DH,(bb2.x+bb2.w)*DW,(bb2.y+bb2.h/2)*DH,aa2.color,0);}}
  drawParticles();drawFlywheel(phase);drawDataLabels(phase);
  dx.font='500 12px monospace';dx.fillStyle=TXT4;dx.fillText('capture > process > store > train > deploy',DW*0.08,DH*0.95);
  dx.font='9px monospace';dx.fillStyle=TXTS4;dx.fillText('EgoVerse-compatible episode format (zarr + SQL)',DW*0.08,DH*0.95+16);
  document.getElementById('pv-0').textContent=phase>=0?Math.min(Math.floor(t2*59.5/75*phase),3596):'0';
  document.getElementById('pv-1').textContent=phase>=1?'42':'0';
  document.getElementById('pv-2').textContent=phase>=3?'7':'0';
  document.getElementById('pv-3').textContent=phase>=5?Math.min(phase-4,15):'0';
  document.getElementById('pv-4').textContent=phase>=8?'0.587':'--';
  for(var i4=0;i4<5;i4++){document.getElementById('ps-'+i4).className=phase>=[0,1,3,5,8][i4]?'ps lit':'ps';}
  document.getElementById('flytext').textContent=flyMsgs[Math.min(phase,flyMsgs.length-1)];
  requestAnimationFrame(anim4);
}
anim4();
})();

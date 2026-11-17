// Чистые функции: работают в браузере и Node.js. Возвращают валидный SVG.
const suits={
 S:'M50 3 C38 22 8 38 8 61 C8 86 37 94 48 74 C45 87 40 93 33 98 H67 C60 93 55 87 52 74 C63 94 92 86 92 61 C92 38 62 22 50 3Z',
 H:'M50 94 C42 83 6 58 6 31 C6 4 36 -3 50 20 C64 -3 94 4 94 31 C94 58 58 83 50 94Z',
 D:'M50 2 L91 50 L50 98 L9 50Z',
 C:'M50 4 C26 4 24 31 37 42 C10 28 -5 56 11 73 C22 84 40 77 47 66 C44 84 40 92 32 98 H68 C60 92 56 84 53 66 C60 77 78 84 89 73 C105 56 90 28 63 42 C76 31 74 4 50 4Z'
};
const unoColors={red:'#e23b3b',yellow:'#f2c200',green:'#3aaa3a',blue:'#2f6fe0'};
const top=`<svg xmlns="http://www.w3.org/2000/svg" width="256" height="358" viewBox="0 0 256 358">`;
const paper=`<defs><filter id="shadow" x="-10%" y="-10%" width="120%" height="125%"><feDropShadow dx="0" dy="2" stdDeviation="1.5" flood-opacity=".17"/></filter></defs><rect x="3" y="3" width="250" height="350" rx="15" fill="#fffaf0" stroke="#d9cfbc" stroke-width="2" filter="url(#shadow)"/>`;
export function pokerFace({rank='A',suit='S',color}={}){
 if(!['2','3','4','5','6','7','8','9','T','J','Q','K','A'].includes(rank))throw Error('Недопустимый rank');
 if(!suits[suit])throw Error('Масть: C D H S');
 color??=(suit==='H'||suit==='D')?'#c0392b':'#1a1a1a';
 if(!['#c0392b','#1a1a1a'].includes(color))throw Error('Недопустимый color');
 const label=rank==='T'?'10':rank;
 return top+paper+`<g fill="${color}"><text x="22" y="80" font-family="Palatino Linotype,Palatino,Georgia,serif" font-size="76" font-weight="700">${label}</text><path d="${suits[suit]}" transform="translate(19 92) scale(.54)"/><path d="${suits[suit]}" transform="translate(70 184) scale(1.16)"/></g></svg>`;
}
function symbol(kind,n,color){
 if(kind==='number')return `<text x="128" y="241" text-anchor="middle" fill="${color}" font-family="Arial,sans-serif" font-size="158" font-weight="700">${n}</text>`;
 if(kind==='skip')return `<g fill="none" stroke="${color}" stroke-width="16"><circle cx="128" cy="180" r="51"/><path d="M92 217 L164 143"/></g>`;
 if(kind==='reverse')return `<g fill="${color}"><path d="M88 115 H157 V91 L192 127 L157 163 V139 H88Z"/><path d="M168 245 H99 V269 L64 233 L99 197 V221 H168Z"/></g>`;
 if(kind==='draw2')return `<g fill="${color}" stroke="#fffaf0" stroke-width="3"><rect x="81" y="144" width="64" height="95" rx="8" transform="rotate(-14 113 191)"/><rect x="116" y="128" width="64" height="95" rx="8" transform="rotate(10 148 175)"/></g>`;
 return `<g transform="translate(70 121)"><path d="M58 0 A58 58 0 0 1 116 58 H58Z" fill="${unoColors.red}"/><path d="M116 58 A58 58 0 0 1 58 116 V58Z" fill="${unoColors.yellow}"/><path d="M58 116 A58 58 0 0 1 0 58 H58Z" fill="${unoColors.green}"/><path d="M0 58 A58 58 0 0 1 58 0 V58Z" fill="${unoColors.blue}"/></g>`+(kind==='wild4'?'<text x="128" y="203" text-anchor="middle" font-family="Arial,sans-serif" font-weight="700" font-size="61" fill="#fff" stroke="#1a1a1a" stroke-width="2" paint-order="stroke">+4</text>':'');
}
export function unoFace({color='red',kind='number',number=7}={}){
 if(!unoColors[color])throw Error('Цвет: red yellow green blue');
 if(!['number','skip','reverse','draw2','wild','wild4'].includes(kind))throw Error('Недопустимый kind');
 if(kind==='number'&&(!Number.isInteger(number)||number<0||number>9))throw Error('number: 0–9');
 const wild=kind==='wild'||kind==='wild4',ink=wild?'#262622':unoColors[color];
 const index={number:String(number),skip:'⊘',reverse:'⇄',draw2:'+2',wild:'●',wild4:'+4'}[kind];
 return top+paper+`<rect x="14" y="14" width="228" height="328" rx="11" fill="${ink}"/><ellipse cx="128" cy="179" rx="86" ry="133" transform="rotate(24 128 179)" fill="#fffaf0"/>`+symbol(kind,number,ink)+`<g fill="#fffaf0" font-family="Arial,sans-serif" font-size="39" font-weight="700"><text x="25" y="57">${index}</text><text x="25" y="57" transform="rotate(180 128 179)">${index}</text></g></svg>`;
}
export function svgDataUrl(svg){return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg)}

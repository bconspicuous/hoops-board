import os
import json
W=os.path.dirname(os.path.abspath(__file__))+'/'
tpl=open(W+os.environ.get('TPL','league3_template.html')).read(); head=tpl[:tpl.index('</style>')+8]
body=open(W+os.environ.get('BODY','league3_body.html')).read()
enc=lambda d: json.dumps(d,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')
d1=json.load(open(W+'d1.json')); d2=json.load(open(W+'d2.json'))
html=head+'\n'+body.replace('%%DATA2%%',enc(d2)).replace('%%DATA%%',enc(d1))
open(W+'league10.html','w').write(html); print(len(html))

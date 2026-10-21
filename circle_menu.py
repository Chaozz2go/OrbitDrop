"""Stable categories and their contextual actions/colors."""
HOME=('KONVERTIEREN','BEARBEITEN','TOOLS')
COLORS={'formats':'#7ed9ba','edit':'#ffbe83','tools':'#83baff','files':'#83baff','more':'#83baff','rotate':'#ffbe83','download':'#7ed9ba'}

def home_actions(files,kind,formats):return list(HOME)

def edit_actions(files,kind):
    actions=[]
    if kind=='Bild':
        if len(files)==1:actions.append('ZUSCHNEIDEN')
        actions+=['DREHEN','GRÖSSE']
    elif kind=='Video' and len(files)==1:actions+=['SCHNEIDEN','DREHEN']
    elif kind=='Audio' and len(files)==1:actions+=['SCHNEIDEN']
    elif kind=='PDF':
        actions.append('PDF TEILEN')
        if len(files)>1:actions.append('PDF VERBINDEN')
    return actions

MENU_LABELS={'KONVERTIEREN':'KONVER-\nTIEREN','BEARBEITEN':'BEARBEITEN','ZUSCHNEIDEN':'ZU-\nSCHNEIDEN','EINSTELLUNGEN':'EIN-\nSTELLUNGEN','PDF VERBINDEN':'PDF\nVERBINDEN','PDF TEILEN':'PDF\nTEILEN','90° RECHTS':'90°\nRECHTS','90° LINKS':'90°\nLINKS','VERSCHIEBEN':'VER-\nSCHIEBEN','AUDIO LADEN':'AUDIO\nLADEN','VIDEO LADEN':'VIDEO\nLADEN','LINK LADEN':'LINK\nEINFÜGEN'}

def action_color(node,label):
    if node=='home':return dict(zip(HOME,[COLORS['formats'],COLORS['edit'],COLORS['tools']])).get(label,COLORS['download'] if label in ('AUDIO LADEN','VIDEO LADEN') else COLORS['tools'])
    return COLORS.get(node,COLORS['tools'])

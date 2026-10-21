"""Named Windows virtual keys and deterministic, non-overlapping trigger chords."""
MODIFIERS=('Strg','Alt','Shift')
KEY_CODES={'Shift':0x10,'Strg':0x11,'Alt':0x12,**{chr(code):code for code in range(65,91)},**{str(i):48+i for i in range(10)},**{'F'+str(i):0x6f+i for i in range(1,25)},**{'Num'+str(i):0x60+i for i in range(10)},'Leertaste':0x20,'Tab':0x09,'Feststelltaste':0x14,'Pause':0x13,'Rollen':0x91,'Einfügen':0x2d,'Pos1':0x24,'Ende':0x23,'Bild auf':0x21,'Bild ab':0x22,'Links':0x25,'Rechts':0x27,'Oben':0x26,'Unten':0x28,'Zurücktaste':0x08,'Enter':0x0d}


def normalize_shortcut(value):
    if not isinstance(value,str):raise ValueError('Bitte eine Taste oder Tastenkombination wählen.')
    aliases={key.casefold():key for key in KEY_CODES};aliases.update({'ctrl':'Strg','control':'Strg','space':'Leertaste','return':'Enter'})
    parts=[aliases.get(part.strip().casefold(),part.strip()) for part in value.split('+')]
    if not parts or any(part not in KEY_CODES for part in parts) or len(parts)!=len(set(parts)):raise ValueError('Ungültige Tastenkombination.')
    bases=[part for part in parts if part not in MODIFIERS]
    if len(bases)>1:raise ValueError('Eine Haupttaste mit optional Strg, Alt und Shift wählen.')
    if 'Strg' in parts and 'Alt' in parts:raise ValueError('Strg+Alt bleibt für AltGr reserviert. Bitte eine andere Kombination wählen.')
    if 'Alt' in parts and 'F4' in parts:raise ValueError('Alt+F4 schließt Windows-Fenster. Bitte eine andere Kombination wählen.')
    return '+'.join([key for key in MODIFIERS if key in parts]+bases)


def validate_bindings(values):
    bindings=[normalize_shortcut(values[name]) for name in ('convert_key','edit_key','files_key')]
    sets=[set(binding.split('+')) for binding in bindings]
    for i,left in enumerate(sets):
        for right in sets[i+1:]:
            if left<=right or right<=left:raise ValueError('Belegungen dürfen nicht gleich sein oder einander enthalten (z. B. Shift und Shift+F2).')
    return dict(zip(('convert_key','edit_key','files_key'),bindings))


def polling_keys(values):
    names=set(MODIFIERS)
    for setting in ('convert_key','edit_key','files_key'):names.update(values[setting].split('+'))
    return {key:KEY_CODES[key] for key in names}


def pressed_mode(values,states,previous):
    if states.get('Strg') and states.get('Alt'):return None
    def matches(binding,snapshot):
        parts=set(binding.split('+'))
        return all(snapshot.get(key,False) for key in parts) and all(not snapshot.get(key,False) for key in MODIFIERS if key not in parts)
    for setting,mode in [('convert_key','convert'),('edit_key','edit'),('files_key','files')]:
        binding=values[setting]
        # Changing modifiers while a main key is already down is not a new trigger.
        parts=binding.split('+');edge_keys=[key for key in parts if key not in MODIFIERS] or parts
        if matches(binding,states) and not matches(binding,previous) and any(states.get(k) and not previous.get(k) for k in edge_keys):return mode
    return None

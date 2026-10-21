"""PDF page selection/reordering/duplication/rotation into a fresh output."""
from pathlib import Path
from converter import reserve
from task_runtime import checkpoint


def export_pages(source,entries,options,expected=None):
    import pymupdf
    source=Path(source);s=source.stat()
    if expected and tuple(expected)!=(s.st_size,s.st_mtime_ns):raise ValueError('PDF wurde seit dem Öffnen geändert. Bitte erneut öffnen.')
    if not isinstance(entries,list) or not 1<=len(entries)<=2000:raise ValueError('Bitte 1 bis 2000 Seiten behalten.')
    output=None
    try:
        with pymupdf.open(source) as pdf:
            if pdf.needs_pass or not pdf.is_pdf:raise ValueError('Bitte ein unverschlüsseltes PDF wählen.')
            for entry in entries:
                if not isinstance(entry,dict) or type(entry.get('page')) is not int or not 0<=entry['page']<len(pdf) or entry.get('rotation') not in (0,90,180,270):raise ValueError('Ungültige Seitenauswahl.')
            indices=[];seen=set()
            for entry in entries:
                index=entry['page']
                if index in seen:pdf.fullcopy_page(index);indices.append(len(pdf)-1)
                else:indices.append(index);seen.add(index)
            pdf.select(indices)
            for i,entry in enumerate(entries):
                checkpoint(i/len(entries)*100,'PDF-Seite '+str(i+1));page=pdf[i];page.set_rotation((page.rotation+entry['rotation'])%360)
            output=reserve(source.with_name(source.stem+'_Seiten.pdf'),'.pdf',options.get('output_dir'));pdf.save(output,garbage=4,deflate=True)
        checkpoint(100,'PDF gespeichert');return [str(output)]
    except Exception:
        if output:output.unlink(missing_ok=True)
        raise

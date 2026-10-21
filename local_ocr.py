"""Local image/scan OCR with PyMuPDF's bundled Tesseract engine."""
import io
from pathlib import Path
from PIL import Image,ImageOps
from task_runtime import checkpoint
from converter import reserve
from ocr_data import find_tessdata,LANGUAGES


def settings(language,dpi,tessdata=None):
    if language not in LANGUAGES or not 72<=int(dpi)<=400:raise ValueError('Ungültige OCR-Sprache oder Auflösung (72–400 dpi).')
    folder=Path(tessdata) if tessdata else find_tessdata(language)
    if not folder or not all((folder/(lang+'.traineddata')).is_file() for lang in language.split('+')):raise ValueError('OCR-Sprachdaten fehlen. Im OCR-Fenster Deutsch/Englisch einrichten.')
    return str(folder),int(dpi)


def image_pixmap(source,dpi):
    import pymupdf
    with Image.open(source) as original:
        if getattr(original,'n_frames',1)>1 or original.width*original.height>50_000_000:raise ValueError('OCR benötigt ein Einzelbild bis 50 Megapixel.')
        rgba=ImageOps.exif_transpose(original).convert('RGBA');image=Image.new('RGB',rgba.size,'white');image.paste(rgba,mask=rgba.getchannel('A'));data=io.BytesIO();image.save(data,format='PNG')
    pix=pymupdf.Pixmap(data.getvalue());pix.set_dpi(dpi,dpi);return pix


def page_pixmap(page,dpi):
    import pymupdf
    if page.rect.width*page.rect.height*(dpi/72)**2>50_000_000:raise ValueError('OCR-Seite zu groß. Weniger DPI wählen.')
    return page.get_pixmap(dpi=dpi,alpha=False,colorspace=pymupdf.csRGB)


def is_pdf(source):
    from filetypes import inspect_file
    kind=inspect_file(source).kind
    if kind not in ('Bild','PDF'):raise ValueError('OCR unterstützt Einzelbilder und unverschlüsselte PDFs.')
    return kind=='PDF'


def recognize_text(source,language='deu+eng',dpi=200,tessdata=None,stopped=None):
    import pymupdf
    tessdata,dpi=settings(language,dpi,tessdata);texts=[]
    if is_pdf(source):
        with pymupdf.open(source) as pdf:
            if pdf.needs_pass or len(pdf)>500:raise ValueError('OCR unterstützt unverschlüsselte PDFs bis 500 Seiten.')
            for index,page in enumerate(pdf):
                checkpoint(index/max(1,len(pdf))*100,f'Text erkennen: Seite {index+1}')
                if stopped and stopped.is_set():raise RuntimeError('OCR geschlossen.')
                # Also recognize images on pages which already contain text.
                if page.rect.width*page.rect.height*(dpi/72)**2>50_000_000:raise ValueError('OCR-Seite zu groß. Weniger DPI wählen.')
                textpage=page.get_textpage_ocr(language=language,dpi=dpi,full=False,tessdata=tessdata);texts.append(page.get_text(textpage=textpage,sort=True))
    else:
        pix=image_pixmap(source,dpi)
        with pymupdf.open('pdf',pix.pdfocr_tobytes(language=language,tessdata=tessdata)) as doc:texts.append(doc[0].get_text(sort=True))
    checkpoint(100,'Texterkennung fertig');return '\n\n'.join(texts).strip()


def ocr_pdf(files,values,options):
    import pymupdf
    language=values.get('language','deu+eng');tessdata,dpi=settings(language,values.get('dpi',200),values.get('tessdata'));created=[]
    try:
        for file_index,file in enumerate(files):
            source=Path(file);output=reserve(source.with_name(source.stem+'_OCR.pdf'),'.pdf',options.get('output_dir'));created.append(output)
            with pymupdf.open() as result:
                if is_pdf(source):
                    with pymupdf.open(source) as pdf:
                        if pdf.needs_pass or len(pdf)>500:raise ValueError('OCR unterstützt unverschlüsselte PDFs bis 500 Seiten.')
                        for index,page in enumerate(pdf):
                            checkpoint((file_index+index/max(1,len(pdf)))/len(files)*100,f'OCR: Seite {index+1}');pix=page_pixmap(page,dpi)
                            with pymupdf.open('pdf',pix.pdfocr_tobytes(language=language,tessdata=tessdata)) as recognized:result.insert_pdf(recognized)
                else:
                    checkpoint(message='OCR: '+source.name);pix=image_pixmap(source,dpi)
                    with pymupdf.open('pdf',pix.pdfocr_tobytes(language=language,tessdata=tessdata)) as recognized:result.insert_pdf(recognized)
                result.save(output,garbage=4,deflate=True)
        checkpoint(100,'Durchsuchbare PDF gespeichert');return [str(p) for p in created]
    except Exception:
        for path in created:path.unlink(missing_ok=True)
        raise

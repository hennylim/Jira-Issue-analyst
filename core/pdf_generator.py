import os
import markdown
try:
    from fpdf import FPDF, HTMLMixin
    class HTMLPDF(FPDF, HTMLMixin):
        pass
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

import logging
logger = logging.getLogger(__name__)

def generate_pdf_from_markdown(md_text: str, output_path: str) -> bool:
    """
    마크다운 텍스트를 PDF로 변환하여 저장합니다.
    """
    if not HAS_FPDF:
        logger.error("fpdf2 라이브러리가 설치되지 않았습니다.")
        return False
        
    try:
        # Markdown을 HTML로 변환
        html_text = markdown.markdown(md_text, extensions=['extra', 'codehilite'])
        
        pdf = HTMLPDF()
        pdf.add_page()
        # 한글 폰트 지원을 원할 경우 폰트 추가 로직 필요하지만, 
        # 기본적으로 ASCII 영문이거나 시스템 폰트를 로드해야 함.
        # Docker 환경을 고려하여 폰트 설정은 추후 고도화 시 추가.
        # pdf.add_font('NanumGothic', '', 'NanumGothic.ttf', uni=True)
        # pdf.set_font('NanumGothic', '', 12)
        pdf.set_font("helvetica", size=10)
        
        # HTML 렌더링 (간단한 태그만 지원됨)
        # HTML 처리에 오류가 날 수 있어 plain text 기반 fallback 구성
        try:
            pdf.write_html(html_text)
        except Exception as e:
            logger.warning(f"HTML to PDF 변환 중 문제 발생, Plain text로 변환합니다: {e}")
            pdf.set_font("helvetica", size=10)
            pdf.multi_cell(0, 10, txt=md_text.encode('latin-1', 'replace').decode('latin-1'))

        pdf.output(output_path)
        logger.info(f"PDF 파일 생성 완료: {output_path}")
        return True
    except Exception as e:
        logger.error(f"PDF 생성 중 오류 발생: {e}")
        return False

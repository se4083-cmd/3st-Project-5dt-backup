#!/usr/bin/env python3
"""Build the Korean v2.1 user guide (optional documentation task).

Requires Python and reportlab only for rebuilding the PDF, not for running the app.
Optional setup: python -m pip install reportlab
Use: python scripts/build-guide.py --font-dir /path/to/Pretendard/static
The font folder must contain Pretendard-Regular.ttf and Pretendard-Bold.ttf.
CSFLOW_GUIDE_FONT_DIR is also accepted. Without an explicit folder, docs/fonts/
is checked first, followed by Windows Malgun Gothic and common font locations.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

ROOT = Path(__file__).resolve().parents[1]
W, H, M, CW = 960, 540, 40, 880
TOTAL = 8
PALETTE = {
    'ink': '#29243F', 'muted': '#6C6682', 'purple': '#5844E8',
    'purple_dark': '#3C2BB0', 'lavender': '#EFEBFF', 'bg': '#F5F4FA',
    'line': '#E7E5F0', 'green': '#178061', 'green_bg': '#E8F5EF',
    'amber': '#926414', 'amber_bg': '#FFF3DF', 'red': '#B33D4B',
    'red_bg': '#FCECEF', 'white': '#FFFFFF', 'code': '#27223C',
}


def register_fonts(font_dir: str | None) -> None:
    candidates = []
    if font_dir:
        candidates.append(Path(font_dir))
    if os.getenv('CSFLOW_GUIDE_FONT_DIR'):
        candidates.append(Path(os.environ['CSFLOW_GUIDE_FONT_DIR']))
    candidates.extend([ROOT / 'docs/fonts', ROOT / 'assets/fonts', Path.home() / '.fonts', Path('/usr/local/share/fonts')])
    pairs = [(folder / 'Pretendard-Regular.ttf', folder / 'Pretendard-Bold.ttf') for folder in candidates]
    pairs += [
        (Path('C:/Windows/Fonts/malgun.ttf'), Path('C:/Windows/Fonts/malgunbd.ttf')),
        (Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'), Path('/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf')),
    ]
    pair = next(((regular, bold) for regular, bold in pairs if regular.is_file() and bold.is_file()), None)
    if pair is None:
        raise SystemExit('Korean fonts not found. Pass --font-dir with Pretendard-Regular.ttf and Pretendard-Bold.ttf.')
    pdfmetrics.registerFont(TTFont('GuideRegular', str(pair[0])))
    pdfmetrics.registerFont(TTFont('GuideBold', str(pair[1])))
    pdfmetrics.registerFontFamily('GuideRegular', normal='GuideRegular', bold='GuideBold', italic='GuideRegular', boldItalic='GuideBold')


class Guide:
    def __init__(self, output: Path) -> None:
        output.parent.mkdir(parents=True, exist_ok=True)
        self.canvas = canvas.Canvas(str(output), pagesize=(W, H), pageCompression=1)
        self.canvas.setTitle('CS Flow AI v2.1 - 로컬 API·임시 RAG 기획형 설명서')
        self.canvas.setAuthor('CS Flow AI')
        self.canvas.setSubject('실행 방법, 상담 흐름, 문서 검색과 저장, 수정 위치 및 팀 연결 범위')
        self.bounds = []

    @staticmethod
    def color(name):
        if isinstance(name, str):
            return HexColor(PALETTE.get(name, name))
        return name

    def rect(self, x, top, width, height, fill='white', stroke=None, radius=12):
        c = self.canvas
        c.setFillColor(self.color(fill))
        c.setStrokeColor(self.color(stroke or fill))
        c.setLineWidth(.8)
        c.roundRect(x, H-top-height, width, height, radius, fill=1, stroke=int(bool(stroke)))

    def line(self, x1, top1, x2, top2, ink='line', width=.8):
        self.canvas.setStrokeColor(self.color(ink))
        self.canvas.setLineWidth(width)
        self.canvas.line(x1, H-top1, x2, H-top2)

    def text(self, value, x, top, size=15, ink='ink', bold=False, align='left', footer=False):
        assert size >= 11.5, ('font below minimum', value, size)
        font = 'GuideBold' if bold else 'GuideRegular'
        width = pdfmetrics.stringWidth(value, font, size)
        left = x if align == 'left' else x-width if align == 'right' else x-width/2
        assert left >= 12 and left+width <= W-12, ('horizontal text overflow', value, left, width)
        assert (top+size <= 502 or footer) and top >= 0, ('vertical text overflow', value, top)
        self.canvas.setFont(font, size)
        self.canvas.setFillColor(self.color(ink))
        draw = self.canvas.drawString if align == 'left' else self.canvas.drawRightString if align == 'right' else self.canvas.drawCentredString
        draw(x, H-top-size, value)
        self.bounds.append({'page': self.canvas.getPageNumber(), 'text': value, 'x': left, 'top': top, 'width': width, 'height': size, 'size': size, 'footer': footer})

    def para(self, value, x, top, width, size=15, ink='ink', bold=False, leading=None, max_height=None):
        assert size >= 11.5, ('font below minimum', value, size)
        style = ParagraphStyle('guide', fontName='GuideBold' if bold else 'GuideRegular', fontSize=size,
            leading=leading or size*1.42, textColor=self.color(ink), wordWrap='CJK',
            spaceBefore=0, spaceAfter=0, splitLongWords=True, allowWidows=0, allowOrphans=0)
        paragraph = Paragraph(value.replace('\n', '<br/>'), style)
        _, height = paragraph.wrap(width, 1000)
        assert max_height is None or height <= max_height+.1, ('paragraph overflow', value, height, max_height)
        assert top+height <= 502, ('page overflow', value, top+height)
        assert x >= 12 and x+width <= W-12, ('horizontal paragraph overflow', value, x, width)
        paragraph.drawOn(self.canvas, x, H-top-height)
        self.bounds.append({'page': self.canvas.getPageNumber(), 'text': value, 'x': x, 'top': top, 'width': width, 'height': height, 'size': size, 'footer': False})
        return height

    def pill(self, value, x, top, ink='purple', fill='lavender', size=12, height=27, pad=11):
        width = pdfmetrics.stringWidth(value, 'GuideBold', size)+pad*2
        self.rect(x, top, width, height, fill=fill, radius=height/2)
        self.text(value, x+pad, top+(height-size)/2-1, size, ink, True)
        return width

    def number(self, value, x, top, fill='purple', diameter=30):
        self.canvas.setFillColor(self.color(fill))
        self.canvas.circle(x+diameter/2, H-top-diameter/2, diameter/2, fill=1, stroke=0)
        self.text(value, x+diameter/2, top+6, 12.5, 'white', True, align='center')

    def arrow(self, x1, top1, x2, top2, ink='purple', width=1.7, head=6):
        self.line(x1, top1, x2, top2, ink, width)
        angle = math.atan2(top2-top1, x2-x1)
        for delta in (-math.pi/6, math.pi/6):
            self.line(x2, top2, x2-head*math.cos(angle+delta), top2-head*math.sin(angle+delta), ink, width)

    def title(self, label, heading, subheading=None):
        self.canvas.setFillColor(self.color('bg'))
        self.canvas.rect(0, 0, W, H, fill=1, stroke=0)
        self.text('CS FLOW AI', M, 20, 11.5, 'purple', True)
        self.text('v2.1 · 로컬 API · 임시 RAG', W-M, 20, 11.5, 'muted', align='right')
        self.line(M, 46, W-M, 46)
        self.text(label, M, 60, 12, 'purple', True)
        self.text(heading, M, 83, 27, 'ink', True)
        if subheading:
            self.para(subheading, M, 124, CW, 14.5, 'muted', max_height=41.2)

    def footer(self, page):
        self.line(M, 507, W-M, 507)
        self.text('합성 데이터로 실행하는 로컬 개발 버전', M, 515, 11.5, 'muted', footer=True)
        self.text(f'2026.11.04  |  {page:02d} / {TOTAL:02d}', W-M, 515, 11.5, 'muted', align='right', footer=True)
        self.canvas.showPage()

    def table(self, x, top, widths, headers, rows, row_height=46, header_height=34, size=14.5):
        total_width = sum(widths)
        self.rect(x, top, total_width, header_height, 'lavender', radius=8)
        xx = x
        for value, width in zip(headers, widths):
            self.para(value, xx+13, top+8, width-26, 12.5, 'purple', True, max_height=header_height-11)
            xx += width
        y = top+header_height
        for index, row in enumerate(rows):
            height = row_height[index] if isinstance(row_height, list) else row_height
            self.rect(x, y, total_width, height, 'white', radius=0)
            xx = x
            for col, (value, width) in enumerate(zip(row, widths)):
                self.para(value, xx+13, y+9, width-26, size, 'ink' if col==0 else 'muted', col==0, max_height=height-14)
                xx += width
            self.line(x+13, y+height, x+total_width-13, y+height)
            y += height
        return y

    def cover(self):
        c = self.canvas
        c.setFillColor(self.color('purple'))
        c.rect(0, 0, W, H, fill=1, stroke=0)
        c.setFillColor(Color(.5, .4, 1, .25))
        c.circle(895, 535, 265, fill=1, stroke=0)
        c.setFillColor(Color(.75, .65, 1, .13))
        c.circle(930, 40, 240, fill=1, stroke=0)
        self.text('CS FLOW AI', 44, 32, 17, 'white', True)
        self.pill('v2.1', 185, 30, ink='purple', fill='white', size=13, height=29)
        self.text('LOCAL CUSTOMER OPERATIONS', 46, 103, 12, '#DBD4FF', True)
        self.text('문서를 찾고,', 43, 140, 42, 'white', True)
        self.text('근거로 안내하고,', 43, 194, 42, 'white', True)
        self.text('결과를 저장합니다', 43, 248, 42, 'white', True)
        self.para('L2 자동 안내 · L3 요청 이관\n로컬 API와 임시 RAG를 연결한 개발 버전', 46, 326, 535, 18, '#ECE7FF', leading=28, max_height=58)
        self.rect(644, 133, 272, 282, 'white', radius=19)
        self.text('이번 버전에서 바로 할 수 있는 일', 665, 155, 14.5, 'muted', True)
        items = [('01', '내 문장으로 문의', '질문에 맞는 문서 검색'),
                 ('02', '근거에 따른 안내', '자동 답변 또는 사람 이관'),
                 ('03', '상담 업무 이어가기', '승인 · 후속 · 자동화 제어'),
                 ('04', '처리 결과 보존', '새로고침 후에도 내역 유지')]
        for i, (num, head, body) in enumerate(items):
            y = 194+i*51
            self.number(num, 665, y+1, diameter=27)
            self.text(head, 705, y, 16.5, 'ink', True)
            self.text(body, 705, y+25, 14, 'muted')
        self.pill('실행 · 기능 흐름 · 수정 위치', 46, 427, ink='purple', fill='white', size=13, height=31)
        self.text('Node.js 24  ·  React  ·  SQLite', 46, 478, 13, '#ECE7FF')
        self.text('2026.11.04  |  01 / 08', 916, 478, 12, 'white', align='right')
        c.showPage()

    def workspace(self):
        self.title('01  화면 구성', '기존 화면을 이어가며 실제 처리 흐름을 연결합니다',
            '관리자는 다섯 메뉴에서 업무를 이어가고, 고객은 자신의 문의와 공개된 결과를 확인합니다.')
        self.table(40, 164, [155, 350, 375], ['화면', '주요 작업', '확인하는 결과'], [
            ('운영 홈', '현황 확인 · 합성 문의 시나리오 추가', '자동 안내와 사람 대기열의 현재 상태'),
            ('문의', '인수 · 초안 저장 · 승인 · 응답', '대화, 이관 사유, 사용한 문서 근거'),
            ('후속', '담당자 · 기한 · 공개/내부 메모 관리', '등록 · 진행 · 완료 · 취소 상태'),
            ('제품', '제품 상세 · 개선 제안 · 이상 징후 확인', 'P1/P2 · 관련 합성 문의와 후속 조회'),
            ('운영 설정', '임시 RAG 확인 · 중지 · 검사 · 재개', '문서 검색 결과와 자동화 가동 상태'),
            ('고객 화면', '질문 · 답변 확인 · 재문의 · 사람 연결', '확정 답변과 공개 후속만 표시'),
        ], row_height=41, size=14.5)
        self.rect(40, 458, 880, 39, 'lavender', radius=10)
        self.para('제품 분석은 <b>20개 제품·7일의 기존 합성 자료</b>를 사용합니다. P2의 28일 요건이 부족하면 이력 부족으로 표시합니다.',
            56, 468, 848, 14, 'purple', max_height=23)
        self.footer(2)

    def levels(self):
        self.title('02  자동 안내와 사람 이관', '질문 전체가 허용 범위에 들어와야 자동 완료합니다',
            '문서를 찾은 뒤에도 현재 회차·버전, 본인 주문, 문서 유효성, 자동화 중지와 후속 여부를 함께 확인합니다.')
        self.rect(40, 169, 542, 264, 'white', 'line')
        self.pill('L2 · 저위험 정보 안내', 58, 187)
        self.text('자동 안내할 수 있는 네 가지 범위', 58, 230, 20, 'ink', True)
        rows = [('주문·배송 상태', '본인 합성 주문의 확인된 현재 상태'),
                ('일반 FAQ', '주문과 무관한 등록 질문의 답변'),
                ('교환·반품 절차', '신청 순서와 경로 설명'),
                ('명확한 정책 안내', '유효한 개발용 정책의 허용 조항')]
        for i, (head, body) in enumerate(rows):
            y = 274+i*35
            self.text(head, 59, y, 15, 'purple', True)
            self.text(body, 219, y, 14.5, 'muted')
        self.rect(600, 169, 320, 264, 'amber_bg')
        self.pill('사람 이관', 619, 187, 'amber', '#FFFFFF')
        self.text('L3 자동 결정은 제외합니다', 619, 230, 19, 'amber', True)
        self.para('환불 승인 · 보상 확정\n계정 권리 변경', 619, 270, 280, 15, 'amber', leading=25, max_height=52)
        self.line(619, 328, 900, 328, '#E8D5B1')
        self.text('그 밖의 이관 조건', 619, 340, 14, 'amber', True)
        self.para('사람 요청 · 미완료 필수 후속\n근거 부족 · 정책 충돌 · 예외 판단',
            619, 368, 280, 14.5, 'amber', leading=23, max_height=48)
        self.rect(40, 450, 880, 46, 'lavender', radius=10)
        self.para('<b>안내 완료는 문의에 대한 설명의 완료입니다.</b> 실제 배송 완료·반품 승인·환불 지급을 확정하는 의미가 아닙니다.',
            58, 462, 844, 14.5, 'purple', max_height=27)
        self.footer(3)

    def retrieval(self):
        self.title('03  검색에서 저장까지', '내 질문이 문서 근거와 처리 결과로 이어집니다',
            '자유 문의는 실제 문서 검색을 거칩니다. 검색 성공만으로 자동 완료가 허용되지는 않습니다.')
        cards = [
            (40, 172, '01', '문의 입력', '내 문장과 관련 합성 주문\n질문 전체를 최대 10,000자까지'),
            (342, 172, '02', '개발용 문서 검색', '10개 정책에서 실제 검색\nBM25 점수로 후보 정렬'),
            (644, 172, '03', '근거로 안내 준비', '선택한 조항과 허용된 조회값\nRETRIEVAL_TEMPLATE 방식'),
            (644, 317, '04', '최종 조건 확인', '현재 회차·주문·정책 재확인\n자동 안내 또는 사람 이관'),
            (342, 317, '05', '로컬 DB에 저장', '중복 요청과 이전 버전 확인\n변경 결과를 함께 저장'),
            (40, 317, '06', '고객에게 결과 표시', '확정 답변과 공개 후속\n새로고침 후에도 내역 유지'),
        ]
        for x, y, num, head, body in cards:
            self.rect(x, y, 276, 111, 'white', 'line')
            self.pill(num, x+16, y+14, size=12, height=25, pad=8)
            self.text(head, x+61, y+15, 18, 'ink', True)
            self.para(body, x+17, y+57, 242, 14.5, 'muted', max_height=44)
        self.arrow(320, 227, 337, 227)
        self.arrow(622, 227, 639, 227)
        self.arrow(782, 288, 782, 312)
        self.arrow(639, 372, 622, 372)
        self.arrow(337, 372, 320, 372)
        self.rect(40, 449, 880, 47, 'lavender', radius=10)
        self.para('<b>기본 모드는 검색 근거를 조합하는 방식입니다.</b> OpenAI 모델·임베딩 API를 호출하지 않으며,\n등록된 안내 범위로 설명할 수 없는 질문은 사람 검토로 보냅니다.',
            57, 456, 846, 14, 'purple', leading=19, max_height=39)
        self.footer(4)

    def human(self):
        self.title('04  상담 업무와 운영 제어', '사람이 판단하는 과정도 끝까지 이어집니다',
            '고객 화면에는 확정 답변과 공개 후속을 보여줍니다. 초안·승인 상세·내부 메모는 운영 화면에서 확인합니다.')
        self.rect(40, 170, 536, 326, 'white', 'line')
        steps = [
            ('01', '담당자 인수', '이관 사유와 현재 문의 회차를 확인합니다.'),
            ('02', '초안 저장', '본문을 바꾸면 이전 승인을 다시 받아야 합니다.'),
            ('03', '검토 승인', '본문·근거·회차·후속 상태를 함께 확인합니다.'),
            ('04', '응답 확정', '10분 이내의 현재 승인을 사용합니다.\n같은 회차의 최종 답변은 한 번만 남깁니다.'),
        ]
        for i, (num, head, body) in enumerate(steps):
            y = 190+i*73
            self.number(num, 59, y+1)
            self.text(head, 105, y, 18, 'ink', True)
            self.para(body, 105, y+29, 449, 14.5, 'muted', leading=20, max_height=42)
            if i < 3:
                self.line(73.5, y+37, 73.5, y+65, 'line', 1.5)
        self.rect(594, 170, 326, 152, 'green_bg')
        self.text('후속 업무', 614, 188, 19, 'green', True)
        self.para('등록 > 진행 > 완료 또는 취소\n담당자·기한·공개/내부 메모 관리\n필수 후속이 남아 있으면 해결을 보류',
            614, 226, 286, 14.5, 'green', leading=26, max_height=81)
        self.rect(594, 340, 326, 156, 'amber_bg')
        self.text('자동화 중지와 재개', 614, 358, 19, 'amber', True)
        self.para('중지 사유를 입력해 자동화를 멈춤\n대기 자동 문의는 사람 경로로 전환\n검사 통과 후 관리자가 명시적으로 재개',
            614, 397, 286, 14.5, 'amber', leading=26, max_height=81)
        self.footer(5)

    def running(self):
        self.title('05  처음 실행하기', 'Node.js를 준비한 뒤 두 명령으로 시작합니다',
            'Windows에서는 시작하기.cmd를 실행해도 됩니다. 최초 의존성 설치 때 인터넷 연결이 필요합니다.')
        self.rect(40, 170, 535, 243, 'white', 'line')
        steps = [
            ('1', 'Node.js 24 LTS 설치', '설치 후 VS Code를 다시 열어 주세요.'),
            ('2', '프로젝트 폴더 열기', '압축을 풀고 package.json이 있는 폴더를 엽니다.'),
            ('3', 'VS Code 터미널에서 실행', 'npm ci 다음에 npm run dev를 실행합니다.'),
            ('4', '브라우저 열기', '오른쪽의 로컬 주소로 접속합니다.'),
        ]
        for i, (num, head, body) in enumerate(steps):
            y = 186+i*56
            self.number(num, 58, y+1, diameter=27)
            self.text(head, 101, y, 17, 'ink', True)
            self.text(body, 101, y+27, 14, 'muted')
        self.rect(594, 170, 326, 243, 'code', radius=13)
        self.text('터미널', 615, 190, 12, '#CAC2E2', True)
        self.text('npm ci', 615, 224, 22, 'white', True)
        self.text('npm run dev', 615, 265, 22, 'white', True)
        self.line(615, 312, 899, 312, '#5A536F')
        self.text('접속 주소', 615, 330, 12, '#CAC2E2', True)
        self.text('http://127.0.0.1:5173', 615, 356, 18.5, 'white', True)
        notes = [
            ('다시 실행', 'npm run dev'),
            ('실행 종료', '터미널에서 Ctrl+C'),
            ('문의 시연 초기화', '운영 설정 > 시연 초기화'),
        ]
        for i, (head, body) in enumerate(notes):
            x = 40+i*300
            self.rect(x, 430, 280, 66, 'lavender', radius=10)
            self.text(head, x+16, 440, 12.5, 'purple', True)
            self.text(body, x+16, 465, 14.5, 'purple')
        self.footer(6)

    def editing(self):
        self.title('06  파일과 폴더', '바꾸려는 기능에 맞춰 해당 폴더를 수정합니다',
            '실행 명령은 scripts/, 개발 설명은 docs/에 있습니다. 화면과 데이터, 검색과 저장 로직을 나누었습니다.')
        self.table(40, 165, [162, 328, 390], ['수정할 내용', '파일 또는 폴더', '수정할 때 확인할 점'], [
            ('화면 · 버튼', 'frontend/src/components/', '입력 폼과 업무 동작, 메뉴 구성'),
            ('색상 · 배치', 'frontend/src/styles/', '각 컴포넌트의 CSS도 함께 확인'),
            ('프런트 API 호출', 'frontend/src/lib/api/', '팀의 인증·경로·응답 형식으로 변환'),
            ('서버 · 저장', 'backend/src/ · database/', '상태 변경과 DB 저장 경계 유지'),
            ('상담 업무 규칙', 'shared/operations/', '승인·회차·후속·중지 조건 확인'),
            ('검색 · 응답 생성', 'ai/rag/', '검색 결과와 근거 검증 형식 유지'),
            ('RAG 정책 문서', 'data/rag/policies/', '본문 수정 후 버전과 해시 갱신'),
            ('제품 분석 · 연결', 'data/analytics/', 'data/operations/에 운영 문의 연결 분리'),
        ], row_height=36, header_height=32, size=14)
        self.footer(7)

    def next_steps(self):
        self.title('07  다음 개발 단계', '연결 모듈을 교체하며 팀 서비스로 이어갑니다',
            '근거 변경·중복 요청·재문의·중지·고객 공개 범위를 점검한 로컬 합성 개발 버전입니다.')
        self.rect(40, 170, 431, 211, 'white', 'line')
        self.pill('현재 동작', 59, 188, 'green', 'green_bg')
        self.text('화면에서 실제 처리와 저장까지', 59, 229, 20, 'ink', True)
        self.para('로컬 API · SQLite 지속 저장\n실제 문서 검색 · 근거에 묶인 안내\n상담 승인 · 후속 관리 · 자동화 중지\n제품 분석·P1/P2·관련 합성 문의 조회',
            59, 271, 392, 15, 'muted', leading=25, max_height=101)
        self.rect(489, 170, 431, 211, 'lavender')
        self.pill('팀 연결 필요', 508, 188, 'purple', 'white')
        self.text('정식 인증·검색·저장·발송', 508, 229, 20, 'purple', True)
        self.para('실제 JWT와 고객·직원 권한\nFastAPI/PostgreSQL · 작업 큐와 worker\n승인된 정책 · 정식 RAG와 생성 모델\n실제 고객 채널 · Fabric 연동',
            508, 271, 392, 15, 'purple', leading=25, max_height=101)
        labels = [('01', '프런트 API 연결', '인증·경로·응답 규격 맞추기'),
                  ('02', '정식 RAG 교체', '승인 문서·검색·생성 연결'),
                  ('03', '저장·발송 검증', '회차·잠금·중복 처리 확인')]
        for i, (num, head, body) in enumerate(labels):
            x = 40+i*300
            self.rect(x, 401, 280, 94, 'white', 'line', radius=11)
            self.text(num, x+15, 414, 12, 'purple', True)
            self.text(head, x+48, 412, 17, 'ink', True)
            self.text(body, x+15, 453, 14, 'muted')
        self.footer(8)

    def build(self):
        for page in [self.cover, self.workspace, self.levels, self.retrieval, self.human, self.running, self.editing, self.next_steps]:
            page()
        self.canvas.save()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font-dir')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/CS_Flow_v2_1_guide_20261104.pdf')
    parser.add_argument('--qa-dir', type=Path)
    args = parser.parse_args()
    register_fonts(args.font_dir)
    guide = Guide(args.output)
    guide.build()
    if args.qa_dir:
        args.qa_dir.mkdir(parents=True, exist_ok=True)
        (args.qa_dir / 'layout-bounds.json').write_text(json.dumps(guide.bounds, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'pages': TOTAL, 'minimum_font_pt': min(x['size'] for x in guide.bounds), 'layout_blocks': len(guide.bounds)}, ensure_ascii=False))


if __name__ == '__main__':
    main()

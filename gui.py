"""Native Qt control panel. The worker remains a separate, single-instance process."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from PySide6.QtCore import Qt,QTimer,QLockFile
from PySide6.QtGui import QColor
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QLabel,QPushButton,
    QVBoxLayout,QHBoxLayout,QGridLayout,QFrame,QRadioButton,QButtonGroup,QCheckBox,
    QLineEdit,QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,
    QPlainTextEdit,QSpinBox,QProgressBar,QComboBox,QScrollArea,QStackedWidget,QAbstractSpinBox)

from config import ROOT,HUNT_SUMMON_MAX_PER_SLOT
from fish_catalog import CATALOG,BY_ID,COLORS,DEFAULT_IDS,name_key
from hunt_catalog import KNOWN, slug, load_seen, forget_seen
from timing_store import TimingStore
from main import RUNTIME,read_status,rotate_log

COLOR_HEX={'beyaz':'#d0d6e2','yesil':'#69d79e','mavi':'#73adff','mor':'#c49aff',
           'kirmizi':'#fa8585','sari':'#f0c76d'}
STYLE='''
QWidget { background:#101722; color:#e8edf5; font-family:"Noto Sans"; font-size:12px; }
QMainWindow { background:#0b111b; }
QFrame[card="true"] { background:#151f2e; border:1px solid #253349; border-radius:12px; }
QLabel { background:transparent; border:0; }
QLabel[muted="true"] { color:#93a4ba; }
QLabel[eyebrow="true"] { color:#6edab4; font-size:11px; font-weight:700; }
QPushButton { background:#243247; color:#ebf1f8; border:1px solid #35465c; border-radius:8px; padding:10px 13px; font-weight:600; }
QPushButton:hover { background:#304159; border-color:#58718a; }
QPushButton:disabled { color:#6b7d91; background:#172231; border-color:#253346; }
QPushButton[primary="true"] { background:#66d5af; color:#102b24; border-color:#66d5af; padding:13px; font-size:14px; }
QPushButton[primary="true"]:hover { background:#82e5c2; }
QPushButton[danger="true"] { background:#392530; color:#ffadb5; border-color:#633342; }
QPushButton[danger="true"]:disabled { background:#172231; color:#6b7d91; border-color:#253346; }
QLineEdit,QSpinBox,QComboBox { background:#0e1723; border:1px solid #304057; border-radius:7px; padding:8px; color:#ecf1f8; }
QLineEdit:focus,QSpinBox:focus { border-color:#63cfa9; }
QRadioButton,QCheckBox { background:transparent; spacing:8px; padding:4px 0; }
QCheckBox::indicator,QRadioButton::indicator { width:16px; height:16px; background:#0e1622; border:1px solid #52667e; border-radius:4px; }
QRadioButton::indicator { border-radius:8px; }
QCheckBox::indicator:checked { background:#65d7af; border:1px solid #65d7af; image:url("@CHECK@"); }
QRadioButton::indicator:checked { background:#65d7af; border:3px solid #223e3a; }
QTableWidget { background:#111b29; alternate-background-color:#152031; border:1px solid #263449; border-radius:8px; selection-background-color:#27403e; gridline-color:#263449; }
QTableWidget::item { padding:6px; border-bottom:1px solid #1e2b3c; }
QTableWidget::indicator { width:14px; height:14px; background:#0e1622; border:1px solid #52667e; border-radius:4px; }
QTableWidget::indicator:checked { background:#65d7af; border:1px solid #65d7af; image:url("@CHECK@"); }
QHeaderView::section { background:#1b293b; color:#aebed1; border:0; padding:9px 5px; font-size:11px; font-weight:600; }
QTableCornerButton::section { background:#1b293b; border:0; }
QPlainTextEdit { background:#0b1420; color:#a9bdd1; border:1px solid #27364b; border-radius:8px; padding:7px; font-size:11px; }
QProgressBar { background:#202e40; border:0; border-radius:5px; min-height:10px; max-height:10px; }
QProgressBar::chunk { background:#66d5af; border-radius:5px; }
QScrollBar:vertical { background:#101a27; width:11px; border:0; }
QScrollBar::handle:vertical { background:#40536b; border-radius:5px; min-height:30px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QPushButton[ghost="true"] { background:transparent; border:1px solid #35465c; color:#c9d6e6; padding:6px 12px; font-weight:500; }
QPushButton[ghost="true"]:hover { background:#1d2a3c; border-color:#58718a; }
QPushButton[modecard="true"] { background:#151f2e; border:1px solid #2a3b52; border-radius:18px; text-align:left; padding:0; }
QPushButton[modecard="true"]:hover { background:#1a2a3d; border-color:#66d5af; }
QFrame[tile="true"] { background:#121c2a; border:1px solid #253349; border-radius:10px; }
QSpinBox { padding:6px 4px; }
QScrollArea { border:0; }
'''


def label(text,point=None,muted=False):
    widget=QLabel(text)
    if point:
        widget.setStyleSheet(f'font-size:{point}px; font-weight:{700 if point>=16 else 500};')
    if muted:widget.setProperty('muted',True)
    return widget


def note(text,lines):
    widget=label(text,muted=True);widget.setWordWrap(True);widget.setMinimumHeight(lines*17+2)
    return widget

def card():
    frame=QFrame();frame.setProperty('card',True)
    return frame

def stepper(spin,width=None):
    """Küçük − [n] + sayaç: ok düğmeleri kaybolan QSpinBox yerine büyük, dokunması kolay düğmeler."""
    spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons);spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    box=QWidget();box.setStyleSheet('background:transparent;')
    row=QHBoxLayout(box);row.setContentsMargins(0,0,0,0);row.setSpacing(4)
    minus=QPushButton('−');plus=QPushButton('+')
    for button,step in ((minus,-1),(plus,1)):
        button.setFixedSize(30,32);button.setProperty('ghost',True);button.setAutoRepeat(True);button.setStyleSheet('padding:0;font-size:15px;')
        button.clicked.connect(lambda _=False,s=step:spin.stepBy(s))
    if width:spin.setFixedWidth(width)
    row.addWidget(minus);row.addWidget(spin);row.addWidget(plus)
    return box


class ControlWindow(QMainWindow):
    def __init__(self,root=ROOT,status_reader=read_status):
        super().__init__()
        self.root=Path(root);self.runtime=self.root/'runtime';self.runtime.mkdir(exist_ok=True)
        self.fishes=tuple(sorted(CATALOG,key=lambda fish:fish.mastery))
        self.status_reader=status_reader
        self.timings=TimingStore(self.runtime/'timings.json')
        self.worker=None;self.pending_launch=None;self.launch_deadline=0
        self.ui_error=''
        self.log_offset=0;self.last_row_data=None;self.start_wait_until=0
        self._docked={};self._seen_mtime=None
        self.setWindowTitle('Ejderhalar Mirası · Kontrol Paneli')
        self.setMinimumSize(1180,780);self.resize(1280,880)
        self.setStyleSheet(STYLE.replace('@CHECK@',(ROOT/'assets'/'check.png').as_posix()))
        container=QWidget();outer=QVBoxLayout(container);outer.setContentsMargins(24,20,24,20);outer.setSpacing(16)
        self.setCentralWidget(container)
        header=QHBoxLayout();title_box=QVBoxLayout();title_box.setSpacing(3)
        eyebrow=label('EJDERHALAR MİRASI');eyebrow.setProperty('eyebrow',True)
        title_box.addWidget(eyebrow)
        self.mode_title=label('Kontrol paneli',27);title_box.addWidget(self.mode_title)
        self.mode_subtitle=label('Bir mod seç.',muted=True)
        title_box.addWidget(self.mode_subtitle)
        header.addLayout(title_box);header.addStretch()
        self.back_button=QPushButton('← Mod seç');self.back_button.setProperty('ghost',True)
        self.back_button.setToolTip('Meslek / Avlan seçimine dön. Bot çalışırken kullanılamaz.')
        self.back_button.clicked.connect(self.show_launcher)
        header.addWidget(self.back_button,0,Qt.AlignmentFlag.AlignTop)
        badge=label('F8 duraklat / devam   ·   F9 durdur',muted=True);header.addWidget(badge,0,Qt.AlignmentFlag.AlignTop)
        outer.addLayout(header)

        # Mod değişkeni: görünmez radyolar. Gerçek seçim kartlardan / Mod seç ekranından gelir.
        self.mode_fishing=QRadioButton('Meslek');self.mode_hunt=QRadioButton('Avlan')
        self.work_group=QButtonGroup(self)
        self.work_group.addButton(self.mode_fishing);self.work_group.addButton(self.mode_hunt)
        self.mode_fishing.setChecked(True)
        self.mode_fishing.hide();self.mode_hunt.hide()

        self.stack=QStackedWidget();outer.addWidget(self.stack,1)
        self.launcher_page=self.build_launcher()
        self.fishing_page=QWidget();self.hunt_page=QWidget()
        self.stack.addWidget(self.launcher_page);self.stack.addWidget(self.fishing_page);self.stack.addWidget(self.hunt_page)

        # ---- Ortak parçalar: her iki sayfada da aynı nesneler kullanılır (durum, günlük, düğmeler, sınırlar)
        self.build_shared()
        # ---- Meslek sayfası
        self.build_fishing_page()
        # ---- Avlan sayfası
        self.build_hunt_page()

        self.by_color.toggled.connect(self.selection_changed);self.by_name.toggled.connect(self.selection_changed)
        self.mode_hunt.toggled.connect(self.apply_mode)
        self.table.itemChanged.connect(self.item_changed);self.search.textChanged.connect(self.filter_rows)
        self.clear_button.clicked.connect(self.clear_selection)
        self.all_button.clicked.connect(self.select_all)
        self.start_button.clicked.connect(self.start_worker);self.pause_button.clicked.connect(self.pause_worker)
        self.stop_button.clicked.connect(self.stop_worker);self.sound_button.clicked.connect(self.test_sound)
        self.load_preferences();self.selection_changed()
        self.sync_seen_creatures()
        state=self.status_reader()
        if state.get('running'):
            # Panel çalışan botun üstüne açıldı: doğrudan o modun sayfasına git.
            self.choose_mode(state.get('mode')=='hunt')
        else:
            self.show_launcher()
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(600);self.refresh()

    # ------------------------------------------------------------------ ekranlar
    def mode_card(self,title,subtitle,text,hunt):
        button=QPushButton();button.setProperty('modecard',True);button.setFixedSize(380,210)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        lay=QVBoxLayout(button);lay.setContentsMargins(26,22,26,22);lay.setSpacing(6)
        badge=label(' ');badge.setProperty('eyebrow',True)
        head=label(title,30);sub=label(subtitle,muted=True);body=label(text,muted=True);body.setWordWrap(True)
        for widget in (badge,head,sub,body):widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        lay.addWidget(badge);lay.addWidget(head);lay.addWidget(sub);lay.addSpacing(6);lay.addWidget(body);lay.addStretch()
        button.clicked.connect(lambda _=False:self.choose_mode(hunt))
        button.badge=badge
        return button

    def build_launcher(self):
        page=QWidget();lay=QVBoxLayout(page);lay.setContentsMargins(0,0,0,0);lay.setSpacing(18)
        lay.addStretch(1)
        heading=label('Ne yapmak istiyorsun?',24);heading.setAlignment(Qt.AlignmentFlag.AlignCenter);lay.addWidget(heading)
        hint=label('Modu seç; panel yalnızca o modun ayarlarını gösterir. Dilediğin zaman “Mod seç” ile dönebilirsin.',muted=True)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter);lay.addWidget(hint)
        row=QHBoxLayout();row.setSpacing(24);row.addStretch()
        self.card_fishing=self.mode_card('Meslek','Balıkçılık','Renk ya da balık türü seç. Enerji, kıymık ve otomatik toplama akışını bot yönetir.',False)
        self.card_hunt=self.mode_card('Avlan','Yaratık avı','Haritadaki yaratıkları seç. Otomatik savaş, binek ve provokasyonla dövüşü bot yürütür.',True)
        row.addWidget(self.card_fishing);row.addWidget(self.card_hunt);row.addStretch();lay.addLayout(row)
        lay.addStretch(2)
        return page

    def build_shared(self):
        """Durum kartları, günlük, düğmeler ve genel ayarlar: tek nesne, aktif sayfaya yerleştirilir."""
        self.monitor_top=QWidget();top=QVBoxLayout(self.monitor_top);top.setContentsMargins(0,0,0,0);top.setSpacing(12)
        stats=QHBoxLayout();stats.setSpacing(10);self.stat_values={};self.stat_titles={}
        for key,title in [('cycles','Tamamlanan döngü'),('attempts','Toplama denemesi'),('last','Son ölçüm'),('scrolls','Kaydırma')]:
            frame=card();layout=QVBoxLayout(frame);layout.setContentsMargins(14,10,14,10)
            title_label=label(title,muted=True);title_label.setWordWrap(True);layout.addWidget(title_label);value=label('—',20)
            layout.addWidget(value);self.stat_values[key]=value;self.stat_titles[key]=title_label;stats.addWidget(frame)
        top.addLayout(stats)
        live=card();live_layout=QVBoxLayout(live);live_layout.setContentsMargins(14,11,14,11);live_layout.setSpacing(5)
        self.status_label=label('Hazır — hedefini seçip başlat.',13);self.status_label.setWordWrap(True);live_layout.addWidget(self.status_label)
        self.progress_text=label('Süreler, toplama penceresi açılıp kapandıkça ölçülür.',muted=True);self.progress_text.setWordWrap(True);live_layout.addWidget(self.progress_text)
        self.progress=QProgressBar();self.progress.setTextVisible(False);self.progress.setValue(0);live_layout.addWidget(self.progress)
        self.energy_text=label('Meslek enerjisi: başlangıçta okunacak.',muted=True);self.energy_text.setWordWrap(True);live_layout.addWidget(self.energy_text)
        self.energy_progress=QProgressBar();self.energy_progress.setTextVisible(False);self.energy_progress.setValue(0);live_layout.addWidget(self.energy_progress)
        top.addWidget(live)

        self.log_box=QWidget();log_layout=QVBoxLayout(self.log_box);log_layout.setContentsMargins(0,0,0,0);log_layout.setSpacing(6)
        log_layout.addWidget(label('CANLI GÜNLÜK',muted=True))
        self.log=QPlainTextEdit();self.log.setReadOnly(True);self.log.setMaximumBlockCount(400);self.log.setMinimumHeight(110)
        log_layout.addWidget(self.log,1)

        self.start_button=QPushButton('Toplamayı başlat');self.start_button.setProperty('primary',True)
        self.pause_button=QPushButton('Duraklat');self.stop_button=QPushButton('Durdur');self.stop_button.setProperty('danger',True)
        self.action_card=card();action_layout=QVBoxLayout(self.action_card)
        action_layout.setContentsMargins(14,14,14,14);action_layout.setSpacing(8)
        action_layout.addWidget(self.start_button);actions=QHBoxLayout();actions.addWidget(self.pause_button);actions.addWidget(self.stop_button);action_layout.addLayout(actions)
        self.sound_button=QPushButton('Alarm sesini dene');action_layout.addWidget(self.sound_button)
        note=label('Bot koruması çıkarsa alarm verir; sen çözünce devam eder.',muted=True)
        note.setWordWrap(True);action_layout.addWidget(note)

        self.general_card=card();general=QVBoxLayout(self.general_card);general.setContentsMargins(16,14,16,14);general.setSpacing(8)
        general.addWidget(label('GENEL AYARLAR',muted=True))
        self.auto_scroll=QCheckBox('Nehirde otomatik kaydır');self.auto_scroll.setChecked(True);general.addWidget(self.auto_scroll)
        self.minimize=QCheckBox('Başlatınca paneli küçült');self.minimize.setChecked(True);general.addWidget(self.minimize)
        limits=QGridLayout();limits.addWidget(label('Döngü sınırı',muted=True),0,0);limits.addWidget(label('Dakika sınırı',muted=True),1,0)
        self.cycle_limit=QSpinBox();self.cycle_limit.setRange(0,9999);self.cycle_limit.setSpecialValueText('Sınırsız')
        self.minute_limit=QSpinBox();self.minute_limit.setRange(0,1440);self.minute_limit.setSpecialValueText('Sınırsız')
        limits.addWidget(stepper(self.cycle_limit,76),0,1);limits.addWidget(stepper(self.minute_limit,76),1,1);general.addLayout(limits)

    def dock(self,widget,layout):
        old=self._docked.get(widget)
        if old is layout:return
        if old is not None:old.removeWidget(widget)
        layout.addWidget(widget);self._docked[widget]=layout

    def build_fishing_page(self):
        body=QHBoxLayout(self.fishing_page);body.setContentsMargins(0,0,0,0);body.setSpacing(16)
        left=card();left.setFixedWidth(275);controls=QVBoxLayout(left);controls.setContentsMargins(18,18,18,18);controls.setSpacing(11)
        scroll_controls=QScrollArea();scroll_controls.setWidgetResizable(True);scroll_controls.setFixedWidth(295)
        scroll_controls.setFrameShape(QFrame.Shape.NoFrame);scroll_controls.setWidget(left)
        sidebar=QVBoxLayout();sidebar.setSpacing(12);sidebar.addWidget(scroll_controls,1);body.addLayout(sidebar)
        self.fs_action=QVBoxLayout();self.fs_action.setContentsMargins(0,0,0,0);sidebar.addLayout(self.fs_action)

        controls.addWidget(label('HEDEF SEÇİMİ',muted=True))
        self.by_color=QRadioButton('Renge göre');self.by_name=QRadioButton('Balık adına göre')
        self.mode_group=QButtonGroup(self);self.mode_group.addButton(self.by_color);self.mode_group.addButton(self.by_name)
        modes=QHBoxLayout();modes.addWidget(self.by_color);modes.addWidget(self.by_name);controls.addLayout(modes)
        self.color_checks={};color_grid=QGridLayout();color_grid.setSpacing(3)
        for i,(color,title) in enumerate(COLORS.items()):
            checkbox=QCheckBox(title);checkbox.setStyleSheet('color:'+COLOR_HEX[color]+';')
            self.color_checks[color]=checkbox;color_grid.addWidget(checkbox,i//2,i%2)
            checkbox.toggled.connect(self.selection_changed)
        controls.addLayout(color_grid)
        self.selection_summary=label('');self.selection_summary.setWordWrap(True);controls.addWidget(self.selection_summary)
        explain=label('Türleri sağdaki kutulardan seçebilirsin. Bot her hedefin rengini ve adını kontrol eder.',muted=True)
        explain.setWordWrap(True);controls.addWidget(explain)
        line=QFrame();line.setFrameShape(QFrame.Shape.HLine);controls.addWidget(line)
        self.energy_cycle=QCheckBox('Enerji dolunca otomatik topla');self.energy_cycle.setChecked(True);controls.addWidget(self.energy_cycle)
        controls.addWidget(label('Enerjiyle toplanacak balık',muted=True))
        self.auto_fish=QComboBox()
        for fish in self.fishes:
            self.auto_fish.addItem(fish.name,fish.id)
        self.auto_fish.setCurrentIndex(self.auto_fish.findData('elmas_som'))
        self.auto_fish.setToolTip('Bu seçim normal avlanma hedefinden bağımsızdır. Enerji dolunca bu tür toplanır.')
        controls.addWidget(self.auto_fish)
        self.auto_splinter=QCheckBox('Kıymığı gider ve oltayı tak');self.auto_splinter.setChecked(True);controls.addWidget(self.auto_splinter)
        self.energy_cycle.toggled.connect(self.auto_fish.setEnabled)
        energy_note=label('Başlangıçta enerji oyundan okunur. Dolunca seçilen balık toplanır, ardından Avlan ekranına dönülür.',muted=True)
        energy_note.setWordWrap(True);controls.addWidget(energy_note)
        mastery_row=QHBoxLayout();mastery_row.addWidget(label('Ustalığım',muted=True));mastery_row.addStretch()
        self.mastery=QSpinBox();self.mastery.setRange(-1,1000);self.mastery.setSpecialValueText('Belirtilmedi');self.mastery.setValue(-1);self.mastery.setFixedWidth(96)
        self.mastery.setToolTip('Meslek ustalığını yazarsan daha yüksek ustalık isteyen türler atlanır.')
        mastery_row.addWidget(stepper(self.mastery,96));controls.addLayout(mastery_row)
        self.fs_general=QVBoxLayout();self.fs_general.setContentsMargins(0,0,0,0);controls.addLayout(self.fs_general)
        controls.addStretch()

        right=QVBoxLayout();right.setSpacing(12);body.addLayout(right,1)
        self.fs_top=QVBoxLayout();self.fs_top.setContentsMargins(0,0,0,0);right.addLayout(self.fs_top)
        table_top=QHBoxLayout();table_top.addWidget(label('Balıklar ve süreleri',14));table_top.addStretch()
        self.search=QLineEdit();self.search.setPlaceholderText('Balık ara…');self.search.setMaximumWidth(230);table_top.addWidget(self.search)
        self.all_button=QPushButton('Tümünü seç');table_top.addWidget(self.all_button)
        self.clear_button=QPushButton('Seçimi temizle');table_top.addWidget(self.clear_button);right.addLayout(table_top)
        self.table=QTableWidget(len(self.fishes),7)
        self.table.setHorizontalHeaderLabels(['Seç','Balık','Renk','Ustalık','Ekrandaki süre','Ölçülen ort.','Örnek'])
        self.table.verticalHeader().setVisible(False);self.table.setShowGrid(False);self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        for col,width in [(0,38),(2,96),(3,51),(4,100),(5,100),(6,47)]:self.table.setColumnWidth(col,width)
        self.table.setMinimumHeight(220)
        self.name_checked=set(DEFAULT_IDS)
        self.hunt_custom=set()
        self._populate()
        right.addWidget(self.table,1)
        footer=label('Ekrandaki süreler başlangıç değerleridir; ölçülen ortalamalar her balık için ayrı güncellenir.\nİnsanlar / Magmarlar aynı tür altında gösterilir. Boş süreler ilk toplamada ölçülür.',muted=True)
        footer.setWordWrap(True);right.addWidget(footer)
        self.fs_log=QVBoxLayout();self.fs_log.setContentsMargins(0,0,0,0);right.addLayout(self.fs_log)
        self.dock(self.monitor_top,self.fs_top);self.dock(self.log_box,self.fs_log)
        self.dock(self.action_card,self.fs_action);self.dock(self.general_card,self.fs_general)

    def build_hunt_page(self):
        root=QHBoxLayout(self.hunt_page);root.setContentsMargins(0,0,0,0);root.setSpacing(16)
        # ---- Sütun 1: av hedefi
        col_a=QVBoxLayout();col_a.setSpacing(12);root.addLayout(col_a)
        target=card();target.setFixedWidth(330);tl=QVBoxLayout(target);tl.setContentsMargins(16,14,16,14);tl.setSpacing(8)
        tl.addWidget(label('AV HEDEFİ',muted=True))
        self.hunt_all=QCheckBox('Tüm yaratıklar')
        self.hunt_all.setToolTip('Haritadaki her yaratığa saldırır; listedeki seçimler yok sayılır.')
        self.hunt_all.toggled.connect(self.hunt_all_toggled)
        tl.addWidget(self.hunt_all)
        tl.addWidget(note('Her harita farklıdır. Yeni haritada bir süre “Tüm yaratıklar” ile gez; saldırılan türler listeye eklenir, sonra tek tek seçebilirsin.',4))
        self.hunt_checks={}
        self.hunt_list_widget=QWidget();self.hunt_list_widget.setStyleSheet('background:#111b29;')
        self.hunt_list=QVBoxLayout(self.hunt_list_widget);self.hunt_list.setContentsMargins(10,8,10,8);self.hunt_list.setSpacing(2)
        self.hunt_list.addStretch(1)
        self.hunt_scroll=QScrollArea();self.hunt_scroll.setWidgetResizable(True);self.hunt_scroll.setWidget(self.hunt_list_widget)
        self.hunt_scroll.setMinimumHeight(150);self.hunt_scroll.setStyleSheet('QScrollArea{border:1px solid #263449;border-radius:8px;background:#111b29;}')
        tl.addWidget(self.hunt_scroll,1)
        self.hunt_summary=label('',muted=True);tl.addWidget(self.hunt_summary)
        pick=QHBoxLayout();pick.setSpacing(6)
        self.hunt_select_all=QPushButton('Tümünü seç');self.hunt_select_none=QPushButton('Temizle')
        for button in (self.hunt_select_all,self.hunt_select_none):button.setProperty('ghost',True);pick.addWidget(button)
        tl.addLayout(pick)
        self.hunt_input=QLineEdit();self.hunt_input.setPlaceholderText('Yaratık adı yaz…')
        self.hunt_input.setToolTip('Haritadaki yaratığın adını yazıp Ekle’ye bas; listede işaretlenebilir çıkar.')
        add_row=QHBoxLayout();add_row.setSpacing(6);add_row.addWidget(self.hunt_input,1)
        self.hunt_add=QPushButton('Ekle');add_row.addWidget(self.hunt_add)
        self.hunt_remove=QPushButton('Kaldır')
        self.hunt_remove.setToolTip('Yazılan adı listeden siler (hazır katalog türleri silinemez).')
        add_row.addWidget(self.hunt_remove);tl.addLayout(add_row)
        levels=QGridLayout();levels.setHorizontalSpacing(8)
        self.hunt_min=QSpinBox();self.hunt_min.setRange(0,999);self.hunt_min.setSpecialValueText('Yok')
        self.hunt_max=QSpinBox();self.hunt_max.setRange(0,999);self.hunt_max.setSpecialValueText('Yok')
        self.hunt_min.setToolTip('Bu seviyenin altındaki yaratıklara saldırmaz.')
        self.hunt_max.setToolTip('Bu seviyenin üstündeki yaratıklara saldırmaz.')
        levels.addWidget(label('En az seviye',muted=True),0,0);levels.addWidget(stepper(self.hunt_min),0,1)
        levels.addWidget(label('En çok seviye',muted=True),1,0);levels.addWidget(stepper(self.hunt_max),1,1)
        tl.addLayout(levels)
        col_a.addWidget(target,1)
        self.hs_general=QVBoxLayout();self.hs_general.setContentsMargins(0,0,0,0);col_a.addLayout(self.hs_general)

        # ---- Sütun 2: dövüş seçenekleri
        col_b=QVBoxLayout();col_b.setSpacing(10);root.addLayout(col_b)
        fight=card();fight.setFixedWidth(370);fl=QVBoxLayout(fight);fl.setContentsMargins(16,14,16,14);fl.setSpacing(10)
        fl.addWidget(label('DÖVÜŞ SEÇENEKLERİ',muted=True))
        fl.addWidget(label('Dövüş başlayınca bot bunları sırayla uygular.',muted=True))
        self.auto_battle_cb=QCheckBox('Otomatik savaş')
        self.auto_battle_cb.setToolTip('Dövüş başlayınca sol araç çubuğundaki otomatik savaş düğmesine basar.')
        fl.addWidget(self.option_tile('#4fd08a',self.auto_battle_cb,'Sol çubuktaki yeşil çapraz kılıç düğmesi. Dövüşü oyun kendi yürütür.'))
        self.mount_cb=QCheckBox('Binek çağır')
        self.mount_cb.setToolTip('Dövüş başlayınca binek düğmesine basar; binek sizinle savaşır.')
        fl.addWidget(self.option_tile('#e45b5b',self.mount_cb,'Sol çubuktaki kırmızı binek düğmesi. Binek seninle birlikte savaşır.'))
        self.provoke_cb=QCheckBox('Provokasyon (ek yaratık çağır)')
        self.provoke_cb.setToolTip('Dövüş başlayınca provokasyonu açıp seçtiğin slotlardan yaratık çağırır (jeton harcar).')
        provoke_tile,provoke_body=self.option_tile('#8f7dff',self.provoke_cb,'Savaşa fazladan yaratık çağırır. Her çağrı jeton harcar.',return_body=True)
        fl.addWidget(provoke_tile)
        self.provoke_row=QWidget();self.provoke_row.setStyleSheet('background:transparent;')
        pv=QVBoxLayout(self.provoke_row);pv.setContentsMargins(0,4,0,0);pv.setSpacing(5)
        pv.addWidget(note('Hangi slottan kaç yaratık? Sıra, çağırma çubuğundaki kartların soldan sağa sırasıdır.',2))
        self.provoke_spins=[]
        for slot in range(5):
            spin=QSpinBox();spin.setRange(0,HUNT_SUMMON_MAX_PER_SLOT);spin.setFixedWidth(52)
            spin.setToolTip(f'{slot+1}. slottan kaç yaratık çağrılsın. 0 = bu slot atlanır.')
            spin.valueChanged.connect(self.provoke_changed)
            self.provoke_spins.append(spin)
            row=QHBoxLayout();row.setSpacing(8)
            row.addWidget(label(f'{slot+1}. slot'+(' (en sol)' if slot==0 else '')));row.addStretch();row.addWidget(stepper(spin))
            pv.addLayout(row)
        self.provoke_total=label('',muted=True);pv.addWidget(self.provoke_total)
        pv.addWidget(note('Slot sayacı dolunca ya da jeton bitince bot o slotta durur, sonrakine geçer. Kilitli slotlar atlanır.',3))
        provoke_body.addWidget(self.provoke_row)
        fl.addStretch(1)
        col_b.addWidget(fight,1)
        # ---- Sütun 3: izleme
        col_c=QVBoxLayout();col_c.setSpacing(12);root.addLayout(col_c,1)
        self.hs_top=QVBoxLayout();self.hs_top.setContentsMargins(0,0,0,0);col_c.addLayout(self.hs_top)
        self.hs_log=QVBoxLayout();self.hs_log.setContentsMargins(0,0,0,0);col_c.addLayout(self.hs_log,1)
        self.hs_action=QVBoxLayout();self.hs_action.setContentsMargins(0,0,0,0);col_c.addLayout(self.hs_action)

        self.hunt_add.clicked.connect(self.hunt_add_creature)
        self.hunt_remove.clicked.connect(self.hunt_remove_creature)
        self.hunt_input.returnPressed.connect(self.hunt_add_creature)
        self.hunt_select_all.clicked.connect(lambda:self.hunt_set_all(True))
        self.hunt_select_none.clicked.connect(lambda:self.hunt_set_all(False))
        self.provoke_cb.toggled.connect(self.provoke_changed)
        for species in KNOWN:self.add_creature_box(species.id,species.name,True)
        self.provoke_changed()

    def option_tile(self,accent,checkbox,text,return_body=False):
        frame=QFrame();frame.setProperty('tile',True)
        row=QHBoxLayout(frame);row.setContentsMargins(0,0,12,0);row.setSpacing(12)
        bar=QFrame();bar.setFixedWidth(5);bar.setStyleSheet(f'background:{accent};border:0;border-top-left-radius:10px;border-bottom-left-radius:10px;')
        row.addWidget(bar)
        body=QVBoxLayout();body.setContentsMargins(0,10,0,10);body.setSpacing(3);row.addLayout(body,1)
        checkbox.setStyleSheet('font-weight:700;font-size:13px;')
        body.addWidget(checkbox)
        desc=note(text,2);body.addWidget(desc)
        return (frame,body) if return_body else frame

    def _populate(self):
        self.table.blockSignals(True)
        for row,fish in enumerate(self.fishes):
            check=QTableWidgetItem();check.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Checked if fish.id in self.name_checked else Qt.CheckState.Unchecked)
            self.table.setItem(row,0,check)
            for col,text in [(1,fish.name),(2,COLORS.get(fish.color,'—')),(3,str(fish.mastery)),
                             (4,f'{fish.base_seconds:g} sn' if fish.base_seconds else '—'),(5,'Ölçülmedi'),(6,'0')]:
                item=QTableWidgetItem(text);item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
                if col>=2:item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col==2 and fish.color:item.setForeground(QColor(COLOR_HEX[fish.color]))
                item.setToolTip(fish.name+(f' · {fish.variants}' if fish.variants else ''))
                self.table.setItem(row,col,item)
            self.table.setRowHeight(row,34)
        self.table.blockSignals(False)

    def selection(self):
        return {'mode':'color' if self.by_color.isChecked() else 'name',
                'colors':[c for c,w in self.color_checks.items() if w.isChecked()],
                'fish':[f.id for f in self.fishes if f.id in self.name_checked]}


    # ------------------------------------------------------------ mod ve sayfalar
    def show_launcher(self):
        self.stack.setCurrentWidget(self.launcher_page)
        self.back_button.setVisible(False)
        self.mode_title.setText('Kontrol paneli')
        self.mode_subtitle.setText('Bir mod seç; ayarlar seçtiğin moda göre açılır.')
        self.setWindowTitle('Ejderhalar Mirası · Kontrol Paneli')
        self.card_hunt.badge.setText('SON KULLANILAN' if self.mode_hunt.isChecked() else ' ')
        self.card_fishing.badge.setText('SON KULLANILAN' if self.mode_fishing.isChecked() else ' ')

    def choose_mode(self,hunt):
        (self.mode_hunt if hunt else self.mode_fishing).setChecked(True)
        self.apply_mode()

    def apply_mode(self,*args):
        """Seçilen modun sayfasını gösterir; ortak parçaları (durum, günlük, düğmeler) oraya taşır."""
        if not hasattr(self,'table') or not hasattr(self,'hs_general'):return
        on=self.mode_hunt.isChecked()
        prefix='hs' if on else 'fs'
        for widget,slot in ((self.monitor_top,'top'),(self.log_box,'log'),(self.action_card,'action'),(self.general_card,'general')):
            self.dock(widget,getattr(self,f'{prefix}_{slot}'))
        self.stack.setCurrentWidget(self.hunt_page if on else self.fishing_page)
        self.back_button.setVisible(True)
        self.mode_title.setText('Avlan · Yaratık avı' if on else 'Meslek · Balıkçılık')
        self.mode_subtitle.setText('Yaratıkları seç, dövüş seçeneklerini işaretle. Bot saldırır, dövüşü izler.'
                                   if on else 'Renk ya da tür seç. Gerçek toplama sürelerini takip et.')
        self.auto_scroll.setText('Haritada otomatik kaydır' if on else 'Nehirde otomatik kaydır')
        self.setWindowTitle('Ejderhalar Mirası · '+('Avlan' if on else 'Meslek'))
        self.hunt_all_toggled(self.hunt_all.isChecked())
        self.provoke_changed()
        self.selection_changed()

    def provoke_changed(self,*args):
        if not hasattr(self,'provoke_total'):return
        on=self.provoke_cb.isChecked()
        self.provoke_row.setEnabled(on)
        total=sum(spin.value() for spin in self.provoke_spins)
        self.provoke_total.setText(f'Toplam: {total} yaratık çağrılacak.' if on else 'Provokasyon kapalı; slot adetleri kullanılmaz.')

    # ------------------------------------------------------------------ yaratık listesi
    def add_creature_box(self,key,name,checked,custom=False):
        checkbox=QCheckBox(name);checkbox.setChecked(checked)
        checkbox.toggled.connect(self.update_hunt_summary)
        self.hunt_checks[key]=checkbox
        if custom:self.hunt_custom.add(key)
        self.hunt_list.insertWidget(max(0,self.hunt_list.count()-1),checkbox)
        self.update_hunt_summary()
        return checkbox

    def update_hunt_summary(self,*args):
        if not hasattr(self,'hunt_summary'):return
        chosen=sum(1 for w in self.hunt_checks.values() if w.isChecked())
        self.hunt_summary.setText('Tüm yaratıklar saldırı listesinde.' if self.hunt_all.isChecked()
                                  else f'{chosen} / {len(self.hunt_checks)} tür seçili')

    def hunt_set_all(self,on):
        for checkbox in self.hunt_checks.values():checkbox.setChecked(on)

    def sync_seen_creatures(self):
        """Botun saldırırken öğrendiği yaratık adlarını (runtime/creatures.json) listeye ekler."""
        path=self.runtime/'creatures.json'
        try:stamp=path.stat().st_mtime_ns
        except OSError:stamp=None
        if stamp==self._seen_mtime:return
        self._seen_mtime=stamp
        for name in load_seen(path):
            key=slug(name)
            if key and key not in self.hunt_checks:
                self.add_creature_box(key,name,False,custom=True)

    def hunt_all_toggled(self,on):
        """'Tüm yaratıklar' işaretliyken liste soluk ve etkisiz görünür; bot yine tümüne saldırır."""
        if not hasattr(self,'hunt_list_widget'):return
        self.hunt_list_widget.setEnabled(not on)
        self.hunt_select_all.setEnabled(not on);self.hunt_select_none.setEnabled(not on)
        self.update_hunt_summary()

    def hunt_add_creature(self):
        """Yazılan özel yaratığı listeye işaretlenebilir kutu olarak ekler."""
        name=self.hunt_input.text().strip()
        if not name:return
        key=slug(name)
        if not key or key in self.hunt_checks:
            self.hunt_input.clear();return
        self.add_creature_box(key,name,True,custom=True)
        self.hunt_input.clear()

    def hunt_remove_creature(self):
        """Yazılan özel yaratığı listeden siler; hazır katalog türleri kalır."""
        name=self.hunt_input.text().strip()
        key=slug(name) if name else ''
        checkbox=self.hunt_checks.get(key)
        if checkbox is None or key not in self.hunt_custom:
            return
        self.hunt_checks.pop(key);self.hunt_custom.discard(key)
        self.hunt_list.removeWidget(checkbox);checkbox.deleteLater()
        forget_seen(self.runtime/'creatures.json',checkbox.text())
        self.hunt_input.clear();self.update_hunt_summary()

    def selection_changed(self,*args):
        if not hasattr(self,'table'):return
        selection=self.selection();colored=selection['mode']=='color'
        for checkbox in self.color_checks.values():checkbox.setEnabled(colored)
        self.table.blockSignals(True)
        for row,fish in enumerate(self.fishes):
            item=self.table.item(row,0)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled|(Qt.ItemFlag.ItemIsUserCheckable if not colored else Qt.ItemFlag.NoItemFlags))
            chosen=self.timings.color(fish.id) in selection['colors'] if colored else fish.id in self.name_checked
            item.setCheckState(Qt.CheckState.Checked if chosen else Qt.CheckState.Unchecked)
        self.table.blockSignals(False)
        self.selection_summary.setText(', '.join(COLORS[c] for c in selection['colors']) if colored
                                       else f'{len(selection["fish"])} balık türü seçili')
        self.clear_button.setEnabled(not colored)
        self.all_button.setEnabled(not colored)

    def item_changed(self,item):
        if item.column()!=0 or not self.by_name.isChecked():return
        fish_id=self.fishes[item.row()].id
        if item.checkState()==Qt.CheckState.Checked:self.name_checked.add(fish_id)
        else:self.name_checked.discard(fish_id)
        self.selection_changed()

    def clear_selection(self):
        self.name_checked.clear();self.selection_changed()

    def select_all(self):
        self.name_checked=set(BY_ID);self.selection_changed()

    def filter_rows(self,text):
        key=name_key(text)
        for row,fish in enumerate(self.fishes):
            self.table.setRowHidden(row,key not in name_key(' '.join((fish.name,*fish.aliases))))

    def load_preferences(self):
        try:prefs=json.loads((self.runtime/'preferences.json').read_text())
        except (OSError,ValueError):prefs={'mode':'color','colors':['yesil'],'fish':list(DEFAULT_IDS)}
        self.name_checked={i for i in prefs.get('fish',DEFAULT_IDS) if i in BY_ID}
        for c,w in self.color_checks.items():w.setChecked(c in prefs.get('colors',['yesil']))
        (self.by_name if prefs.get('mode')=='name' else self.by_color).setChecked(True)
        self.auto_scroll.setChecked(prefs.get('auto_scroll',True));self.minimize.setChecked(prefs.get('minimize',True))
        self.cycle_limit.setValue(prefs.get('max_cycles',0));self.minute_limit.setValue(prefs.get('max_minutes',0))
        self.mastery.setValue(prefs.get('mastery',-1))
        self.energy_cycle.setChecked(prefs.get('energy_cycle',True))
        self.auto_splinter.setChecked(prefs.get('auto_splinter',True))
        index=self.auto_fish.findData(prefs.get('auto_fish','elmas_som'))
        self.auto_fish.setCurrentIndex(index if index>=0 else self.auto_fish.findData('elmas_som'))
        self.auto_fish.setEnabled(self.energy_cycle.isChecked())
        self.hunt_all.setChecked(prefs.get('hunt_all',False))
        chosen=set(prefs.get('hunt_creatures',[s.id for s in KNOWN]))
        for key,checkbox in list(self.hunt_checks.items()):checkbox.setChecked(key in chosen)
        for name in prefs.get('hunt_custom',[]):
            key=slug(str(name))
            if key and key not in self.hunt_checks:
                self.add_creature_box(key,str(name),key in chosen,custom=True)
        self.hunt_min.setValue(prefs.get('hunt_min',0));self.hunt_max.setValue(prefs.get('hunt_max',0))
        saved_counts=prefs.get('hunt_provoke_counts',[1,0,0,0,0])
        for spin,value in zip(self.provoke_spins,list(saved_counts)+[0]*(5-len(saved_counts))):
            spin.setValue(int(value))
        self.auto_battle_cb.setChecked(prefs.get('hunt_auto_battle',True))
        self.mount_cb.setChecked(prefs.get('hunt_mount',True))
        self.provoke_cb.setChecked(prefs.get('hunt_provoke',True))
        self.mode_fishing.setChecked(not prefs.get('hunt_mode',False))
        self.mode_hunt.setChecked(prefs.get('hunt_mode',False))
        self.hunt_all_toggled(self.hunt_all.isChecked())
        self.provoke_changed()

    def save_preferences(self):
        prefs=self.selection()|{'auto_scroll':self.auto_scroll.isChecked(),'minimize':self.minimize.isChecked(),
                               'max_cycles':self.cycle_limit.value(),'max_minutes':self.minute_limit.value(),
                               'mastery':self.mastery.value(), 'energy_cycle':self.energy_cycle.isChecked(),
                               'auto_fish':self.auto_fish.currentData(),'auto_splinter':self.auto_splinter.isChecked(),
                               'hunt_mode':self.mode_hunt.isChecked(),'hunt_all':self.hunt_all.isChecked(),
                               'hunt_creatures':[key for key,w in self.hunt_checks.items() if w.isChecked()],
                               'hunt_custom':[next(cb.text() for k,cb in self.hunt_checks.items() if k==key)
                                              for key in sorted(self.hunt_custom)],
                               'hunt_min':self.hunt_min.value(),'hunt_max':self.hunt_max.value(),
                               'hunt_auto_battle':self.auto_battle_cb.isChecked(),
                               'hunt_mount':self.mount_cb.isChecked(),
                               'hunt_provoke':self.provoke_cb.isChecked(),
                               'hunt_provoke_counts':[spin.value() for spin in self.provoke_spins]}
        temp=self.runtime/'preferences.tmp';temp.write_text(json.dumps(prefs,ensure_ascii=False,indent=2))
        temp.replace(self.runtime/'preferences.json')

    def worker_command(self):
        if self.mode_hunt.isChecked():
            command=[str(self.root/'run.sh'),'--hunt']
            if self.hunt_all.isChecked():
                command+=['--creatures','all']
            else:
                chosen=[key for key,w in self.hunt_checks.items() if w.isChecked()]
                if not chosen:raise ValueError('Başlatmak için en az bir yaratık seç.')
                # Özel yaratıklar özgün adlarıyla gönderilir; katalog türleri kimlikle.
                command+=['--creatures',*(self.hunt_checks[key].text() if key in self.hunt_custom
                                          else key for key in chosen)]
            if self.hunt_min.value():command+=['--min-level',str(self.hunt_min.value())]
            if self.hunt_max.value():command+=['--max-level',str(self.hunt_max.value())]
            if self.auto_battle_cb.isChecked():command.append('--auto-battle')
            if self.mount_cb.isChecked():command.append('--mount')
            if self.provoke_cb.isChecked():
                counts=[spin.value() for spin in self.provoke_spins]
                if not any(counts):
                    raise ValueError('Provokasyon için en az bir slota çağırma adedi girin.')
                command.append('--provoke')
                if any(counts):
                    command+=['--provoke-counts',','.join(str(c) for c in counts)]
        else:
            selection=self.selection()
            targets=selection['colors'] if selection['mode']=='color' else selection['fish']
            if not targets:raise ValueError('Başlatmak için en az bir renk veya balık seç.')
            command=[str(self.root/'run.sh'),'--colors' if selection['mode']=='color' else '--fish',*targets]
            if self.energy_cycle.isChecked():
                fish=BY_ID[self.auto_fish.currentData()]
                if self.mastery.value()>=0 and fish.mastery>self.mastery.value():
                    raise ValueError(f'{fish.name} için {fish.mastery} ustalık gerekiyor.')
                command+=['--energy-cycle','--auto-fish',fish.id]
            if not self.auto_splinter.isChecked():command.append('--no-auto-splinter')
            if self.mastery.value()>=0:command+=['--mastery',str(self.mastery.value())]
        if not self.auto_scroll.isChecked():command.append('--no-scroll')
        if self.cycle_limit.value():command+=['--max-cycles',str(self.cycle_limit.value())]
        if self.minute_limit.value():command+=['--max-seconds',str(self.minute_limit.value()*60)]
        return command

    def start_worker(self):
        try:command=self.worker_command()
        except ValueError as e:self.status_label.setText(str(e));return
        self.save_preferences()
        state=self.status_reader()
        if state.get('running') or state.get('process_alive'):
            self.pending_launch=command;self.launch_deadline=time.monotonic()+10
            self.send_signal('stop');self.status_label.setText('Yeni seçim uygulanıyor; önceki çalışma durduruluyor…')
        else:self.launch(command)

    def console_output(self):
        # Worker çıktısı da büyür; her açılışta sınırla ki son hata görünür kalsın.
        path=self.runtime/'console.log'
        rotate_log(path)
        return path.open('a')

    def launch(self,command):
        self.ui_error=''
        try:
            with self.console_output() as out:
                self.worker=subprocess.Popen(command,cwd=self.root,stdin=subprocess.DEVNULL,
                                             stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        except OSError as e:
            self.ui_error=f'Başlatılamadı: {e}';self.status_label.setText(self.ui_error);return
        self.start_wait_until=time.monotonic()+8
        self.start_button.setEnabled(False);self.stop_button.setEnabled(True)
        self.status_label.setText('Başlatılıyor; oyun penceresi hazırlanıyor…')
        if self.minimize.isChecked():self.showMinimized()

    def send_signal(self,command):
        state=self.status_reader()
        if state.get('running'):
            try:os.kill(state['pid'],{'stop':signal.SIGTERM,'pause':signal.SIGUSR1,'resume':signal.SIGUSR2}[command])
            except ProcessLookupError:pass
        if command=='stop' and self.worker and self.worker.poll() is None:
            if not state.get('running') or state.get('pid')!=self.worker.pid:
                self.worker.terminate()
        if command=='stop' and not self.pending_launch:self.status_label.setText('Durduruluyor…')

    def stop_worker(self):
        self.pending_launch=None
        self.send_signal('stop')

    def pause_worker(self):
        state=self.status_reader()
        resume=state.get('paused',False)
        self.send_signal('resume' if resume else 'pause')
        if resume and self.minimize.isChecked():self.showMinimized()

    def test_sound(self):
        subprocess.Popen([str(self.root/'run.sh'),'--test-alarm'],cwd=self.root,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def refresh(self):
        state=self.status_reader();running=state.get('running',False)
        if self.pending_launch:
            if self.worker:self.worker.poll()
            if not running and not state.get('process_alive'):
                command=self.pending_launch;self.pending_launch=None;self.launch(command)
            elif time.monotonic()>self.launch_deadline:
                self.pending_launch=None;self.status_label.setText('Önceki süreç durmadı; ikinci bot başlatılmadı.')
            return
        starting=bool(not running and self.worker and self.worker.poll() is None and time.monotonic()<self.start_wait_until)
        self.pause_button.setEnabled(running);self.stop_button.setEnabled(running or starting)
        self.back_button.setEnabled(not running and not starting)
        self.sync_seen_creatures()
        self.start_button.setEnabled(not starting)
        self.pause_button.setText('Devam et' if state.get('paused') else 'Duraklat')
        hunt=state.get('mode')=='hunt' if running else self.mode_hunt.isChecked()
        self.start_button.setText('Seçimi uygula ve başlat' if running else ('Avı başlat' if hunt else 'Toplamayı başlat'))
        self.stat_titles['cycles'].setText('Tamamlanan dövüş' if hunt else 'Tamamlanan döngü')
        self.stat_titles['attempts'].setText('Saldırı denemesi' if hunt else 'Toplama denemesi')
        if running:
            self.start_wait_until=0;self.status_label.setText(state.get('message') or 'Çalışıyor…')
        elif time.monotonic()>self.start_wait_until:
            self.status_label.setText('Hazır — hedefini seçip başlat.' if not state.get('message') else 'Durduruldu · '+state['message'])
        if not running and self.worker and self.worker.poll() not in (None,0,-signal.SIGTERM):
            self.ui_error='Başlatılamadı veya bir hata oluştu. Ayrıntılar: runtime/console.log'
        if self.ui_error:self.status_label.setText(self.ui_error)
        for key,field in [('cycles','completed_cycles'),('attempts','attempts'),('scrolls','scrolls')]:
            self.stat_values[key].setText(str(state.get(field,0)))
        last=state.get('last_measurement');self.stat_values['last'].setText(f'{last["seconds"]:.1f} sn' if last else '—')
        energy=state.get('energy',{})
        if hunt:
            self.energy_progress.setValue(0)
            self.energy_text.setText('Yaratık avında enerji kullanılmaz.')
        elif energy.get('value') is not None:
            self.energy_progress.setMaximum(energy.get('maximum',100));self.energy_progress.setValue(energy['value'])
            suffix=' · tahmini' if energy.get('estimated') else ' · oyundan okundu'
            if not running:suffix=' · son kayıt'
            if running and state.get('profession_phase')=='AUTO_WAIT':suffix=' · son okuma; otomatik toplamada harcanıyor'
            self.energy_text.setText(f'Meslek enerjisi: {energy["value"]}/{energy.get("maximum",100)}{suffix}  |  Oto toplama: {state.get("auto_cycles",0)}  |  Kıymık giderme: {state.get("splinter_recoveries",0)}')
        else:
            self.energy_progress.setValue(0)
            self.energy_text.setText('Meslek enerjisi: okunacak.' if self.energy_cycle.isChecked() else 'Enerji geçişi kapalı.')
        elapsed=state.get('elapsed_seconds');expected=state.get('expected_seconds')
        if running and state.get('phase')=='HARVESTING' and elapsed is not None:
            fish=BY_ID.get(state.get('active_fish_id'));name=fish.name if fish else 'Toplama'
            self.progress_text.setText(f'{name} · {elapsed:.1f} sn geçti'+(f' · yaklaşık {max(0,expected-elapsed):.1f} sn kaldı' if expected else ' · süre ölçülüyor'))
            self.progress.setValue(min(99,int(elapsed/expected*100)) if expected else 0)
        elif running and state.get('profession_phase')=='AUTO_WAIT':
            value,total=state.get('auto_progress'),state.get('auto_total')
            fish=BY_ID.get(state.get('auto_fish_id'))
            self.progress_text.setText(f'{fish.name if fish else "Balık"} · otomatik toplama'+(f' · {value}/{total} sn' if value is not None and total else ' · ekran izleniyor'))
            self.progress.setValue(int(value/total*100) if value is not None and total else 0)
        else:
            self.progress.setValue(0)
            self.progress_text.setText('Dövüş ve haritaya dönüş burada izlenir.' if hunt
                                       else 'Toplama başladığında kalan süre ve ölçüm burada görünür.')
        self.timings.reload()
        summaries=self.timings.all_summaries()
        signature=json.dumps(summaries,sort_keys=True)
        if signature!=self.last_row_data:
            self.table.blockSignals(True)
            for row,fish in enumerate(self.fishes):
                summary=summaries[fish.id];value=summary['mean_seconds']
                self.table.item(row,5).setText(f'{value:.2f} sn' if value is not None else 'Ölçülmedi')
                self.table.item(row,6).setText(str(summary['count']))
                color=self.timings.color(fish.id)
                if color:
                    self.table.item(row,2).setText(COLORS[color])
                    self.table.item(row,2).setForeground(QColor(COLOR_HEX[color]))
                    self.table.item(row,2).setToolTip('Oyun ekranından doğrulandı.' if fish.color else 'Toplama sırasında gözlemlendi.')
                if value is not None:
                    self.table.item(row,5).setToolTip(
                        f'Son: {summary["last_seconds"]:.2f} sn\n'
                        f'En kısa / uzun: {summary["min_seconds"]:.2f} / {summary["max_seconds"]:.2f} sn\n'
                        'Ortalama ve tahmin son 40 geçerli ölçüme dayanır.')
            self.table.blockSignals(False);self.last_row_data=signature;self.selection_changed()
        path=self.runtime/'bot.log'
        if path.exists():
            if path.stat().st_size<self.log_offset:self.log_offset=0
            with path.open() as f:
                f.seek(self.log_offset);text=f.read();self.log_offset=f.tell()
            if text:self.log.appendPlainText(text.rstrip())

    def closeEvent(self,event):
        self.stop_worker()
        self.save_preferences()
        event.accept()


def run_gui():
    app=QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('DWAR Balıkçılık')
    RUNTIME.mkdir(exist_ok=True)
    server_name=f'dwar-fishing-panel-{os.getuid()}'
    socket=QLocalSocket();socket.connectToServer(server_name)
    if socket.waitForConnected(250):
        socket.write(b'show');socket.waitForBytesWritten(300);socket.disconnectFromServer();return 0
    lock=QLockFile(str(RUNTIME/'panel.lock'));lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        print('Kontrol paneli zaten açık.');return 0
    QLocalServer.removeServer(server_name)
    server=QLocalServer()
    if not server.listen(server_name):
        lock.unlock();raise RuntimeError('Kontrol paneli bağlantısı açılamadı.')
    window=ControlWindow()
    def show_existing():
        client=server.nextPendingConnection()
        if client:client.disconnectFromServer();client.deleteLater()
        window.showNormal();window.raise_();window.activateWindow()
    server.newConnection.connect(show_existing)
    window.show()
    try:
        result=app.exec()
    except KeyboardInterrupt:
        # Terminalden Ctrl+C paneli öldürünce slot ortasındaki kesinti
        # traceback süsü vermesin; tercih zaten kaydedilmiştir.
        result=0
    server.close();QLocalServer.removeServer(server_name);lock.unlock()
    return result


if __name__=='__main__':raise SystemExit(run_gui())


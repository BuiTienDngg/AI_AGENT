"""Native Windows/Tk form for the developer to complete the object inventory."""
from __future__ import annotations
import copy
from pathlib import Path

from .core import load_json
from .objects import CATEGORIES, save_review


CATEGORY_LABELS = {
    'player': 'Nhân vật người chơi', 'enemy': 'Kẻ địch / NPC', 'obstacle': 'Vật cản',
    'collectible': 'Vật phẩm thu thập', 'power_up': 'Vật phẩm hỗ trợ', 'terrain': 'Địa hình / đường đi',
    'decoration': 'Cảnh vật / trang trí', 'interactive': 'Đối tượng tương tác', 'ui': 'Giao diện / HUD',
    'other': 'Khác',
}


class ObjectReviewForm:
    def __init__(self, root, workdir, inventory, reasons=()):
        import tkinter as tk
        from tkinter import ttk
        self.root, self.workdir, self.inventory = root, Path(workdir), inventory
        self.rows = copy.deepcopy(inventory['objects'])
        self.editing = None
        self.tk, self.ttk = tk, ttk
        root.title('Slope3 — Bổ sung đối tượng trong game')
        root.geometry('1080x760')
        root.minsize(860, 650)
        root.protocol('WM_DELETE_WINDOW', self.pause)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        ttk.Label(root, text='Kiểm tra danh sách trước khi AI viết bài', font=('Segoe UI', 15, 'bold')).grid(row=0, column=0, sticky='w', padx=16, pady=(14, 6))
        uncertain = sum(bool(row.get('needs_confirmation') or row.get('question')) for row in self.rows)
        explanation = f'Danh sách có {len(self.rows)} đối tượng; {uncertain} mục cần xác nhận. Chọn một dòng để xem câu hỏi và bổ sung thông tin.'
        if reasons and reasons[0].startswith('AI mới'):
            explanation += '\n' + reasons[0]
        ttk.Label(root, text=explanation + '\nCó thể điền tiếng Việt. Nút xác nhận sẽ ghi nhận các mô tả này là thông tin do đội phát triển cung cấp.',
                  wraplength=1020).grid(row=1, column=0, sticky='ew', padx=16, pady=(0, 8))
        table = ttk.Frame(root)
        table.grid(row=2, column=0, sticky='nsew', padx=16)
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(table, columns=('name', 'category', 'status'), show='headings', selectmode='browse', height=9)
        for key, label, width in [('name', 'Tên đối tượng', 350), ('category', 'Nhóm', 220), ('status', 'Trạng thái / Cần xác nhận', 350)]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.tree.bind('<Double-1>', lambda event: self.name_entry.focus_set())
        tools = ttk.Frame(root)
        tools.grid(row=3, column=0, sticky='w', padx=16, pady=8)
        for title, action in [('Thêm mới', self.new), ('Xóa mục đã chọn', self.delete), ('Xem ảnh gameplay', self.show_images)]:
            ttk.Button(tools, text=title, command=action).pack(side='left', padx=(0, 8))
        self.question = tk.StringVar()
        ttk.Label(root, textvariable=self.question, wraplength=1020, foreground='#805000').grid(row=4, column=0, sticky='ew', padx=16, pady=(0, 6))
        fields = ttk.LabelFrame(root, text='Thông tin đối tượng đang chọn')
        fields.grid(row=5, column=0, sticky='ew', padx=16, pady=(0, 10))
        fields.columnconfigure(1, weight=1)
        self.name = tk.StringVar()
        self.category = tk.StringVar(value=CATEGORY_LABELS['other'])
        self.frames = tk.StringVar()
        self.include = tk.BooleanVar(value=True)
        ttk.Label(fields, text='Tên').grid(row=0, column=0, sticky='w', padx=8, pady=5)
        self.name_entry = ttk.Entry(fields, textvariable=self.name)
        self.name_entry.grid(row=0, column=1, sticky='ew', padx=8, pady=5)
        ttk.Label(fields, text='Nhóm').grid(row=1, column=0, sticky='w', padx=8)
        ttk.Combobox(fields, values=list(CATEGORY_LABELS.values()), textvariable=self.category, state='readonly').grid(row=1, column=1, sticky='ew', padx=8)
        ttk.Label(fields, text='Ngoại hình').grid(row=2, column=0, sticky='nw', padx=8, pady=5)
        self.appearance = tk.Text(fields, height=2, wrap='word', font=('Segoe UI', 10))
        self.appearance.grid(row=2, column=1, sticky='ew', padx=8, pady=5)
        ttk.Label(fields, text='Chức năng / cơ chế').grid(row=3, column=0, sticky='nw', padx=8)
        self.behavior = tk.Text(fields, height=3, wrap='word', font=('Segoe UI', 10))
        self.behavior.grid(row=3, column=1, sticky='ew', padx=8)
        ttk.Label(fields, text='Frame minh họa').grid(row=4, column=0, sticky='w', padx=8, pady=5)
        ttk.Entry(fields, textvariable=self.frames).grid(row=4, column=1, sticky='ew', padx=8, pady=5)
        ttk.Label(fields, text='Ví dụ: FRAME001, FRAME004; có thể để trống nếu bạn bổ sung ngoài video.', wraplength=800).grid(row=5, column=1, sticky='w', padx=8)
        ttk.Checkbutton(fields, text='Đưa đối tượng này vào bài viết', variable=self.include).grid(row=6, column=1, sticky='w', padx=8, pady=4)
        ttk.Button(fields, text='Lưu đối tượng', command=self.commit).grid(row=7, column=1, sticky='e', padx=8, pady=(0, 8))
        footer = ttk.Frame(root)
        footer.grid(row=6, column=0, sticky='ew', padx=16, pady=(0, 14))
        ttk.Button(footer, text='Lưu nháp và tạm dừng', command=self.pause).pack(side='left')
        ttk.Button(footer, text='Bỏ qua bổ sung', command=self.skip).pack(side='left', padx=8)
        ttk.Button(footer, text='Xác nhận danh sách và tiếp tục', command=self.confirm).pack(side='right')
        self.refresh()
        if self.rows:
            self.tree.selection_set('0')
            self.select()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for index, row in enumerate(self.rows):
            status = row.get('question_vi') or row.get('question') or ('Cần xác nhận' if row.get('needs_confirmation') else 'Đã quan sát')
            self.tree.insert('', 'end', iid=str(index), values=(row['name'], CATEGORY_LABELS.get(row.get('category'), 'Khác'), status))

    def select(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return
        target = int(selected[0])
        if target != self.editing and self.name.get().strip():
            previous = self.editing
            if not self.commit(quiet=True, refresh=False):
                if previous is not None:
                    self.tree.selection_set(str(previous))
                return
        self.editing = target
        row = self.rows[self.editing]
        question = row.get('question_vi') or row.get('question')
        self.question.set('Cần xác nhận: ' + question if question else 'Bạn có thể sửa tên, mô tả hoặc bổ sung cơ chế cho đối tượng này.')
        self.name.set(row['name'])
        self.category.set(CATEGORY_LABELS.get(row.get('category'), 'Khác'))
        self.frames.set(', '.join(row.get('frame_ids', [])))
        self.include.set(row.get('include_in_article', True))
        for widget, key in [(self.appearance, 'appearance'), (self.behavior, 'observed_behavior')]:
            widget.delete('1.0', 'end')
            widget.insert('1.0', row.get(key, ''))

    def new(self, discard=False):
        if not discard and self.name.get().strip() and not self.commit(quiet=True, refresh=False):
            return
        self.editing = None
        self.tree.selection_remove(*self.tree.selection())
        self.name.set('')
        self.question.set('Điền đối tượng còn thiếu; chức năng bạn xác nhận sẽ được dùng để viết bài.')
        self.category.set(CATEGORY_LABELS['other'])
        self.frames.set('')
        self.include.set(True)
        self.appearance.delete('1.0', 'end')
        self.behavior.delete('1.0', 'end')
        self.name_entry.focus_set()

    def commit(self, quiet=False, refresh=True):
        from tkinter import messagebox
        if not self.name.get().strip():
            if not quiet or self.editing is not None:
                messagebox.showwarning('Thiếu tên', 'Hãy điền tên đối tượng.', parent=self.root)
            return self.editing is None
        import re
        frame_ids = [x.strip().upper() for x in re.split(r'[,;\s]+', self.frames.get()) if x.strip()]
        valid = {x['frame_id'] for x in load_json(self.workdir / 'frames.json')['frames']}
        if set(frame_ids) - valid:
            messagebox.showerror('Frame không tồn tại', ', '.join(sorted(set(frame_ids) - valid)), parent=self.root)
            return False
        original = self.rows[self.editing] if self.editing is not None else {}
        candidate = 1
        used = {r['id'] for r in self.rows}
        while f'OBJ{candidate:03}' in used:
            candidate += 1
        row = {**original, 'id': original.get('id', f'OBJ{candidate:03}'),
               'name': self.name.get().strip(),
               'category': next((k for k, v in CATEGORY_LABELS.items() if v == self.category.get()), 'other'),
               'appearance': self.appearance.get('1.0', 'end').strip(),
               'observed_behavior': self.behavior.get('1.0', 'end').strip(),
               'frame_ids': frame_ids, 'include_in_article': self.include.get()}
        if self.editing is None:
            self.rows.append(row)
            self.editing = len(self.rows) - 1
        else:
            self.rows[self.editing] = row
        if refresh:
            self.refresh()
            self.tree.selection_set(str(self.editing))
        else:
            values = (row['name'], CATEGORY_LABELS.get(row['category'], 'Khác'), row.get('question') or 'Chờ xác nhận')
            if self.tree.exists(str(self.editing)):
                self.tree.item(str(self.editing), values=values)
            else:
                self.tree.insert('', 'end', iid=str(self.editing), values=values)
        return True

    def delete(self):
        if self.editing is not None:
            del self.rows[self.editing]
            self.refresh()
            self.editing = None
            self.new(discard=True)

    def show_images(self):
        import os
        import webbrowser
        folder = self.workdir / 'contact_sheets'
        if folder.is_dir():
            if hasattr(os, 'startfile'):
                os.startfile(str(folder))
            else:
                webbrowser.open(folder.as_uri())

    def finish(self, state):
        from tkinter import messagebox
        if not self.commit(quiet=True):
            return
        try:
            save_review(self.workdir, self.inventory, self.rows, state)
        except ValueError as exc:
            messagebox.showerror('Chưa lưu được', str(exc), parent=self.root)
            return
        self.root.destroy()

    def confirm(self):
        self.finish('confirmed')

    def pause(self):
        self.finish('pending')

    def skip(self):
        # Keep earlier owner confirmations; otherwise discard unfinished manual edits.
        if self.inventory['review']['state'] == 'confirmed':
            save_review(self.workdir, self.inventory, self.inventory['objects'], 'confirmed')
        else:
            analysis = load_json(self.workdir / 'analysis.json', default={})
            rows = analysis.get('game_objects', self.inventory['objects'])
            rows = [row for row in rows if isinstance(row, dict) and str(row.get('name', '')).strip()]
            save_review(self.workdir, self.inventory, rows, 'skipped')
        self.root.destroy()


def open_object_form(workdir, inventory, reasons=()):
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise RuntimeError('Không có giao diện Tk khả dụng trong phiên Windows này.') from exc
    ObjectReviewForm(root, workdir, inventory, reasons)
    root.lift()
    root.mainloop()

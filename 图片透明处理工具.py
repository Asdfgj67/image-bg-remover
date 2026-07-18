"""
图片背景透明处理工具 v1.0
桌面 GUI 程序 - 双击运行，无需终端
使用 tkinter + OpenCV + PIL
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import numpy as np
import cv2
import os
import threading

# ====== 图像处理核心 ======
def process_image(img_array, output_size, bg_threshold, edge_smooth, scale_pct):
    """
    对图像进行背景透明化处理
    img_array: numpy array (H, W, 3) RGB
    output_size: (W, H) 输出尺寸
    bg_threshold: 背景阈值 (230-253)，越高越敏感
    edge_smooth: 边缘平滑 (0-5)
    scale_pct: 缩放比例 (50-100)
    返回: PIL Image RGBA
    """
    H, W = img_array.shape[:2]
    bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 颜色阈值
    _, th1 = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    _, th2 = cv2.threshold(gray, bg_threshold, 255, cv2.THRESH_BINARY_INV)
    thresh = cv2.bitwise_and(th1, th2)

    # 形态学
    k1 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (12, 12))
    k2 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k1, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, k2, iterations=1)

    # 保留主要区域
    n, labels, stats, _ = cv2.connectedComponentsWithStats(thresh, 8)
    if n > 1:
        areas = stats[1:, cv2.CC_STAT_AREA]
        max_a = areas.max()
        th_f = np.zeros_like(thresh)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] > max_a * 0.02:
                th_f[labels == i] = 255
        thresh = th_f

    # GrabCut
    coords = cv2.findNonZero(thresh)
    if coords is not None:
        x, y, rw, rh = cv2.boundingRect(coords)
        m = 8; x = max(1, x-m); y = max(1, y-m)
        rw = min(W-x-1, rw+2*m); rh = min(H-y-1, rh+2*m)

        mask = np.zeros((H, W), np.uint8)
        mask[thresh == 255] = cv2.GC_PR_FGD
        mask[thresh == 0] = cv2.GC_PR_BGD
        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        cv2.grabCut(bgr, mask, (x, y, rw, rh), bgd, fgd, 3, cv2.GC_INIT_WITH_MASK)

        alpha = np.where((mask==cv2.GC_FGD)|(mask==cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        alpha = cv2.bitwise_or(alpha, thresh)

        # 安全移除近白色像素
        alpha[(gray >= bg_threshold + 10) & (alpha > 0)] = 0

        # 边缘处理
        k3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, k3, iterations=1)

        if edge_smooth > 0:
            blur_size = 1 + edge_smooth * 2  # 1, 3, 5, 7, 9, 11
            alpha_f = alpha.astype(np.float32)
            alpha_f = cv2.GaussianBlur(alpha_f, (blur_size, blur_size), edge_smooth)
            inner = cv2.erode(alpha, k3, iterations=edge_smooth)
            alpha = np.where(inner > 0, 255, alpha_f).astype(np.uint8)
    else:
        alpha = np.full((H, W), 0, dtype=np.uint8)

    # 创建 RGBA
    rgba = np.dstack([img_array, alpha])
    img_t = Image.fromarray(rgba, "RGBA")

    # 裁切 + 缩放
    nz = np.nonzero(alpha > 10)
    if len(nz[0]) > 0:
        y1, y2 = nz[0].min(), nz[0].max()
        x1, x2 = nz[1].min(), nz[1].max()
        p = 15
        y1, y2 = max(0, y1-p), min(H, y2+p)
        x1, x2 = max(0, x1-p), min(W, x2+p)
        crop = img_t.crop((x1, y1, x2, y2))

        final = Image.new("RGBA", output_size, (0, 0, 0, 0))
        cw, ch = crop.size
        s = min(output_size[0]/cw, output_size[1]/ch) * (scale_pct / 100.0)
        nw, nh = int(cw*s), int(ch*s)
        rs = crop.resize((nw, nh), Image.LANCZOS)
        px, py = (output_size[0]-nw)//2, (output_size[1]-nh)//2
        final.paste(rs, (px, py), rs)
        return final
    else:
        return Image.new("RGBA", output_size, (0, 0, 0, 0))


# ====== GUI 应用 ======
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("图片背景透明处理工具 v1.0")
        self.root.geometry("880x680")
        self.root.resizable(True, True)
        self.root.minsize(800, 620)

        # 状态变量
        self.original_image = None      # PIL Image (原始)
        self.processed_image = None     # PIL Image RGBA (处理后)
        self.preview_orig_tk = None     # ImageTk
        self.preview_proc_tk = None     # ImageTk

        self.setup_ui()

    def setup_ui(self):
        """构建界面"""
        # 主容器
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # === 标题 ===
        title = ttk.Label(main_frame, text="图片背景透明处理工具",
                         font=("Microsoft YaHei", 14, "bold"))
        title.pack(pady=(0, 10))

        # === 预览区域 ===
        preview_frame = ttk.Frame(main_frame)
        preview_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # 左：原图
        left_frame = ttk.LabelFrame(preview_frame, text="原图", padding=5)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        self.label_orig = ttk.Label(left_frame, text="请选择图片",
                                   background="#f0f0f0", anchor=tk.CENTER,
                                   font=("Microsoft YaHei", 11))
        self.label_orig.pack(fill=tk.BOTH, expand=True)

        # 右：结果
        right_frame = ttk.LabelFrame(preview_frame, text="处理结果", padding=5)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))
        self.label_proc = ttk.Label(right_frame, text="等待处理",
                                   background="#f0f0f0", anchor=tk.CENTER,
                                   font=("Microsoft YaHei", 11))
        self.label_proc.pack(fill=tk.BOTH, expand=True)

        # === 参数控制区 ===
        ctrl_frame = ttk.LabelFrame(main_frame, text="参数设置", padding=10)
        ctrl_frame.pack(fill=tk.X, pady=10)

        # 第1行：输出尺寸
        row1 = ttk.Frame(ctrl_frame)
        row1.pack(fill=tk.X, pady=3)
        ttk.Label(row1, text="输出宽度:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.var_width = tk.IntVar(value=512)
        self.spin_w = ttk.Spinbox(row1, from_=64, to=2048, increment=64,
                                  textvariable=self.var_width, width=6)
        self.spin_w.pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="px", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)

        ttk.Label(row1, text="   输出高度:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT, padx=(15,0))
        self.var_height = tk.IntVar(value=512)
        self.spin_h = ttk.Spinbox(row1, from_=64, to=2048, increment=64,
                                  textvariable=self.var_height, width=6)
        self.spin_h.pack(side=tk.LEFT, padx=5)
        ttk.Label(row1, text="px", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)

        # 第2行：背景阈值
        row2 = ttk.Frame(ctrl_frame)
        row2.pack(fill=tk.X, pady=3)
        ttk.Label(row2, text="背景阈值:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.var_threshold = tk.IntVar(value=242)
        scale_th = ttk.Scale(row2, from_=230, to=253, variable=self.var_threshold,
                            orient=tk.HORIZONTAL, length=250, command=self.on_param_change)
        scale_th.pack(side=tk.LEFT, padx=5)
        self.lbl_th = ttk.Label(row2, text="242", font=("Microsoft YaHei", 10), width=4)
        self.lbl_th.pack(side=tk.LEFT)
        ttk.Label(row2, text="(越高去背景越多)", foreground="gray",
                 font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=5)

        # 第3行：边缘平滑
        row3 = ttk.Frame(ctrl_frame)
        row3.pack(fill=tk.X, pady=3)
        ttk.Label(row3, text="边缘平滑:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.var_smooth = tk.IntVar(value=2)
        scale_sm = ttk.Scale(row3, from_=0, to=5, variable=self.var_smooth,
                            orient=tk.HORIZONTAL, length=250, command=self.on_param_change)
        scale_sm.pack(side=tk.LEFT, padx=5)
        self.lbl_sm = ttk.Label(row3, text="2", font=("Microsoft YaHei", 10), width=4)
        self.lbl_sm.pack(side=tk.LEFT)
        ttk.Label(row3, text="(0=锐利, 5=柔和)", foreground="gray",
                 font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=5)

        # 第4行：缩放比例
        row4 = ttk.Frame(ctrl_frame)
        row4.pack(fill=tk.X, pady=3)
        ttk.Label(row4, text="缩放比例:", font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.var_scale = tk.IntVar(value=92)
        scale_sc = ttk.Scale(row4, from_=50, to=100, variable=self.var_scale,
                            orient=tk.HORIZONTAL, length=250, command=self.on_param_change)
        scale_sc.pack(side=tk.LEFT, padx=5)
        self.lbl_sc = ttk.Label(row4, text="92%", font=("Microsoft YaHei", 10), width=5)
        self.lbl_sc.pack(side=tk.LEFT)
        ttk.Label(row4, text="(角色在画布中占比)", foreground="gray",
                 font=("Microsoft YaHei", 9)).pack(side=tk.LEFT, padx=5)

        # === 按钮区 ===
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=10)

        self.btn_select = ttk.Button(btn_frame, text="选择图片", command=self.select_image)
        self.btn_select.pack(side=tk.LEFT, padx=5)

        self.btn_process = ttk.Button(btn_frame, text="开始处理", command=self.do_process,
                                     state=tk.DISABLED)
        self.btn_process.pack(side=tk.LEFT, padx=5)

        self.btn_save = ttk.Button(btn_frame, text="保存结果", command=self.save_result,
                                  state=tk.DISABLED)
        self.btn_save.pack(side=tk.LEFT, padx=5)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪 - 请选择一张图片")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var,
                              relief=tk.SUNKEN, anchor=tk.W, padding=5,
                              font=("Microsoft YaHei", 9))
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))

    def on_param_change(self, event=None):
        """参数变更时自动更新标签和预览"""
        self.lbl_th.config(text=str(self.var_threshold.get()))
        self.lbl_sm.config(text=str(self.var_smooth.get()))
        self.lbl_sc.config(text=f"{self.var_scale.get()}%")
        # 如果已有原图，自动重新处理
        if self.original_image is not None:
            self.update_preview()

    def select_image(self):
        """选择图片文件"""
        path = filedialog.askopenfilename(
            title="选择图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp"), ("所有文件", "*.*")]
        )
        if not path:
            return

        try:
            self.original_image = Image.open(path).convert("RGB")
            self.status_var.set(f"已加载: {os.path.basename(path)} ({self.original_image.size[0]}x{self.original_image.size[1]})")
            self.btn_process.config(state=tk.NORMAL)
            self.show_original_preview()
            # 自动处理一次
            self.do_process()
        except Exception as e:
            messagebox.showerror("错误", f"无法加载图片:\n{e}")

    def show_original_preview(self):
        """在左侧显示原图预览"""
        if self.original_image is None:
            return
        # 缩放原图以适应预览区
        preview = self.resize_to_fit(self.original_image, 380, 350)
        self.preview_orig_tk = ImageTk.PhotoImage(preview)
        self.label_orig.config(image=self.preview_orig_tk, text="")

    def resize_to_fit(self, img, max_w, max_h):
        """按比例缩放图片以适应指定区域"""
        w, h = img.size
        scale = min(max_w/w, max_h/h)
        if scale < 1:
            return img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
        return img.copy()

    def do_process(self):
        """执行图像处理"""
        if self.original_image is None:
            return

        self.status_var.set("正在处理...")
        self.btn_process.config(state=tk.DISABLED, text="处理中...")
        self.root.update_idletasks()

        try:
            arr = np.array(self.original_image)
            output_size = (self.var_width.get(), self.var_height.get())
            bg_threshold = self.var_threshold.get()
            edge_smooth = self.var_smooth.get()
            scale_pct = self.var_scale.get()

            self.processed_image = process_image(
                arr, output_size, bg_threshold, edge_smooth, scale_pct
            )

            self.show_processed_preview()
            self.btn_save.config(state=tk.NORMAL)
            self.status_var.set(f"处理完成 - {output_size[0]}x{output_size[1]} RGBA")
        except Exception as e:
            messagebox.showerror("错误", f"处理失败:\n{e}")
            self.status_var.set("处理失败")
        finally:
            self.btn_process.config(state=tk.NORMAL, text="开始处理")

    def update_preview(self):
        """静默更新预览（不清除原图，参数变更时调用）"""
        if self.original_image is None:
            return
        try:
            arr = np.array(self.original_image)
            output_size = (self.var_width.get(), self.var_height.get())
            self.processed_image = process_image(
                arr, output_size,
                self.var_threshold.get(),
                self.var_smooth.get(),
                self.var_scale.get()
            )
            self.show_processed_preview()
            self.btn_save.config(state=tk.NORMAL)
        except:
            pass  # 滑动时静默失败

    def show_processed_preview(self):
        """在右侧显示处理结果预览"""
        if self.processed_image is None:
            return
        preview = self.resize_to_fit(self.processed_image, 380, 350)
        # 用棋盘格背景显示透明效果
        checker = self.make_checker_bg(preview.size)
        checker.paste(preview, (0, 0), preview)
        self.preview_proc_tk = ImageTk.PhotoImage(checker)
        self.label_proc.config(image=self.preview_proc_tk, text="")

    def make_checker_bg(self, size, cell=12):
        """创建棋盘格背景（用于显示透明效果）"""
        w, h = size
        bg = Image.new("RGB", (w, h), (255, 255, 255))
        gray = (200, 200, 200)
        for y in range(0, h, cell):
            for x in range(0, w, cell):
                if (x//cell + y//cell) % 2 == 0:
                    for dy in range(cell):
                        for dx in range(cell):
                            if x+dx < w and y+dy < h:
                                bg.putpixel((x+dx, y+dy), gray)
        return bg

    def save_result(self):
        """保存处理结果"""
        if self.processed_image is None:
            return

        path = filedialog.asksaveasfilename(
            title="保存结果",
            defaultextension=".png",
            filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")],
            initialfile="处理结果_透明.png"
        )
        if not path:
            return

        try:
            self.processed_image.save(path, "PNG", optimize=True)
            self.status_var.set(f"已保存: {os.path.basename(path)}")
            messagebox.showinfo("完成", f"图片已保存到:\n{path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败:\n{e}")


def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()

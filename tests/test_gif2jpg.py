from PIL import Image
import numpy as np


def calc_ssim(image1: Image.Image, image2: Image.Image) -> float:
    """计算结构相似性指数（SSIM）

    :param image1: 第一张图像（RGB模式）
    :param image2: 第二张图像（RGB模式）
    :return: SSIM值
    """
    arr1 = np.array(image1)
    arr2 = np.array(image2)

    # 计算均值和方差
    mu1 = np.mean(arr1)
    mu2 = np.mean(arr2)
    sigma1_sq = np.var(arr1)
    sigma2_sq = np.var(arr2)
    sigma12 = np.cov(arr1.flatten(), arr2.flatten())[0, 1]

    # 计算SSIM
    c1 = (0.01 * 255) ** 2
    c2 = (0.03 * 255) ** 2
    return ((2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)) / ((mu1**2 + mu2**2 + c1) * (sigma1_sq + sigma2_sq + c2))


def get_unsim_frames(
    image: Image.Image,
    ssim_threshold: float = 0.75,
    max_num_frames: int = 16,
) -> list[Image.Image]:
    """获取GIF图像中不相似的帧

    :param image_bytes: GIF图像的字节数据
    :param ssim_threshold: SSIM阈值，高于该值的帧将被跳过
    :param max_num_frames: 最大帧数限制
    :return: 不相似的帧列表
    """
    frames = []  # 存储不相似帧的列表

    # 获取GIF的帧数和尺寸
    for i in range(image.n_frames):
        image.seek(i)  # 定位到当前帧
        frame = image.convert("RGB")  # 转换为RGB模式
        frames.append(frame)

    last_decrease_threshold = 0.0  # 上次减少的阈值
    epoch = 1  # 迭代次数

    while len(frames) > max_num_frames:
        remain_frames = [frames[0]]  # 保留第一帧
        for i in range(1, len(frames)):
            # 计算当前帧与最后一帧的SSIM
            ssim = calc_ssim(remain_frames[-1], frames[i])
            if ssim < ssim_threshold:
                remain_frames.append(frames[i])

        # 计算减少的帧数
        last_decrease = len(frames) - len(remain_frames)

        # 若剩余帧数是目标的两倍，则保持减幅
        # 如果上次减少的帧数大于0，则减小减幅
        # 如果上次没有减少，则增加减幅
        if epoch == 1 or last_decrease == 0:
            last_decrease_threshold = min(0.1, last_decrease_threshold + 0.05)
        elif len(frames) <= max_num_frames * 2:
            last_decrease_threshold = max(0.0, last_decrease_threshold - 0.01)

        ssim_threshold -= last_decrease_threshold

        frames = remain_frames
        epoch += 1

    return frames


def _compute_grid_shape(n, width, height, max_rows=4, max_cols=4) -> tuple[int, int]:
    """计算拼接图像的行数和列数
    :param n: 帧数
    :param width: 图像宽度
    :param height: 图像高度
    :param max_rows: 最大行数
    :param max_cols: 最大列数
    :return: (行数, 列数)
    """
    min_area = float("inf")
    best_dist = float("inf")
    best_shape = (max_rows, max_cols)

    for rows in range(1, max_rows + 1):
        for cols in range(1, max_cols + 1):
            if rows * cols >= n:
                area = rows * cols
                dist_to_square = abs(rows * height - cols * width)
                if area < min_area:
                    # 选择更小的布局
                    best_shape = (rows, cols)
                    min_area = area
                    best_dist = dist_to_square
                elif area == min_area and dist_to_square < best_dist:
                    # 选择更接近正方形的布局
                    best_shape = (rows, cols)
                    best_dist = dist_to_square

    return best_shape


def gif2jpg(
    image: Image.Image,
    ssim_threshold: float = 0.75,
    max_frame_matrix: tuple[int, int] = (4, 4),
) -> tuple[Image.Image, int, int, int]:
    """将GIF转换为拼接的静态图像, 跳过相似的帧

    采用MSE和SSIM综合计算相似度-MSE初筛，SSIM精筛

    :param image_bytes: GIF图像的字节数据
    :param ssim_threshold: 相似度阈值，越小越严格
    :param max_frame_matrix: 最大帧矩阵，表示拼接图像的行数和列数
    :return: (拼接后的图像, 拼接图像的横向帧数, 拼接图像的纵向帧数, 拼接图像的总帧数)
    """

    max_frame_num = max_frame_matrix[0] * max_frame_matrix[1]

    # 获取GIF的帧数和尺寸
    width, height = image.size

    frames = get_unsim_frames(image, ssim_threshold, max_frame_num)

    # 计算拼接图像矩阵的行列数
    if len(frames) < max_frame_num:
        # 如果帧数少于最大限制，则计算合适的布局
        rows, cols = _compute_grid_shape(len(frames), width, height, max_frame_matrix[0], max_frame_matrix[1])
    else:
        # 如果帧数超过最大限制，则使用最大限制的布局
        rows, cols = max_frame_matrix

    # 计算拼接图像的尺寸
    new_width = cols * width
    new_height = rows * height

    # 创建新的图像（预先填充白色背景）
    new_image = Image.new("RGB", (new_width, new_height), (0, 0, 0))
    for i, frame in enumerate(frames):
        # 计算当前帧在拼接图像中的位置
        x = (i % cols) * width
        y = (i // cols) * height
        # 将当前帧粘贴到拼接图像中
        new_image.paste(frame, (x, y))

    return new_image, cols, rows, len(frames)


if __name__ == "__main__":
    # Add the parent directory to the system path
    image = Image.open("./tests/test.gif")

    # Convert the GIF to JPG
    jpg_image, rows, cols, num_frames = gif2jpg(image, 0.75)
    # Save the resulting image
    jpg_image.save("./tests/output.jpg")

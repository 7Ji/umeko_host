# Umeko Host

A cross-platform desktop application for USB CDC thermal imaging devices based on Umeko firmware. The currently tested camera uses an Arduino Nano RP2040 Connect and an MLX90640 sensor. The application also supports the MLX90640, MLX90641, and Heimann frame formats identified in the closed-source Windows host application.

用于基于 Umeko 固件的 USB CDC 热成像设备的跨平台桌面上位机。当前测试实机使用 Arduino Nano RP2040 Connect 与 MLX90640；程序也兼容从闭源 Windows 上位机中识别出的 MLX90640、MLX90641 和 Heimann 帧格式。

## Features / 功能

- Automatically discovers serial ports and prioritizes the Arduino Nano RP2040 Connect. / 自动发现串口并优先选择 Arduino Nano RP2040 Connect。
- Displays a live thermal image with maximum, minimum, average, center, and mouse-probe temperatures. / 显示实时热图、最高温、最低温、平均温、中心温和鼠标悬停点温度。
- Provides five palettes, automatic or manual temperature ranges, and nearest-neighbor or bilinear interpolation. / 提供五种色表、自动或手动温度范围，以及最近邻或双线性插值。
- Supports horizontal and vertical flipping plus 0, 90, 180, and 270 degree rotation. / 支持水平翻转、垂直翻转以及 0、90、180 和 270 度旋转。
- Pauses the displayed image without stopping serial reception. / 可暂停显示画面而不中断串口接收。
- Saves the current view as a PNG with a temperature scale or as a coordinate-labelled CSV temperature matrix. / 可将当前画面保存为带温标的 PNG，或保存为带坐标的 CSV 温度矩阵。
- Browses photos stored in the camera's LittleFS and exports raw DAT, temperature CSV, or thermal PNG files. / 可浏览相机 LittleFS 中保存的照片，并导出原始 DAT、温度 CSV 或热图 PNG。
- Batch-exports all photos on the device as DAT, CSV, and PNG files. / 可将设备内全部照片批量导出为 DAT、CSV 和 PNG。
- Provides English and Simplified Chinese interfaces, follows the system language by default, and allows temporary language switching from the toolbar. / 提供英文和简体中文界面，默认跟随系统语言，并可从工具栏临时切换语言。

The application only sends `stream\n`, `stop_stream\n`, the read-only photo-list command `check\n`, and the read-only photo-download command `download photo_N.dat\n`. It does not modify calibration data, the file system, or firmware. The currently tested camera requires `stream\n` to be resent about every 500 ms as a keepalive. For reference firmware that streams continuously on its own, the application detects the stream passively and avoids sending keepalives.

程序只会发送 `stream\n`、`stop_stream\n`、只读照片列表命令 `check\n` 和只读照片下载命令 `download photo_N.dat\n`，不会修改校准数据、文件系统或固件。当前测试实机要求约每 500 ms 重发一次 `stream\n` 作为保活；对于自行连续输出的参考固件，程序会被动识别数据流并避免发送保活命令。

## Running / 运行

Python 3.11 or later is required. Using [uv](https://docs.astral.sh/uv/) is recommended:

需要 Python 3.11 或更高版本。推荐使用 [uv](https://docs.astral.sh/uv/)：

```bash
uv sync --extra test
uv run umeko-host
```

A standard virtual environment can also be used:

也可以使用标准虚拟环境：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
umeko-host
```

Linux users need permission to read and write the serial port. On common distributions, add the user to the `dialout` or `uucp` group. A local device can also be identified through its stable `/dev/serial/by-id/...` path.

Linux 用户需要拥有串口读写权限。常见发行版可将用户加入 `dialout` 或 `uucp` 组；本机设备也可以通过稳定路径 `/dev/serial/by-id/...` 识别。

## Testing / 测试

```bash
QT_QPA_PLATFORM=offscreen uv run pytest
```

Protocol tests use synthetic frames and do not contain thermal images captured from a real device.

协议测试使用合成帧，不包含真实设备采集的热图数据。

## License / 许可证

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE) for the full license text.

本项目按照 GNU 通用公共许可证第 3 版（GPLv3）授权。完整许可条款请参阅 [LICENSE](LICENSE)。

"""
Parses log lines containing ANSI escape codes or Loguru-style color tags
into a list of Flet TextSpan objects for colored output.
"""

import re
import flet as ft

# Basic ANSI SGR (Select Graphic Rendition) codes mapping
# See: https://en.wikipedia.org/wiki/ANSI_escape_code#SGR_(Select_Graphic_Rendition)_parameters
# Focusing on common foreground colors and styles used by Loguru
ANSI_CODES = {
    # Styles
    "1": ft.FontWeight.BOLD,
    "3": ft.TextStyle(italic=True),  # Italic
    "4": ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE),  # Underline
    "22": ft.FontWeight.NORMAL,  # Reset bold
    "23": ft.TextStyle(italic=False),  # Reset italic
    "24": ft.TextStyle(decoration=ft.TextDecoration.NONE),  # Reset underline
    # Foreground Colors (30-37)
    "30": ft.colors.BLACK,
    "31": ft.colors.RED,
    "32": ft.colors.GREEN,
    "33": ft.colors.YELLOW,
    "34": ft.colors.BLUE,
    "35": ft.colors.PINK,
    "36": ft.colors.CYAN,
    "37": ft.colors.WHITE,
    "39": None,  # Default foreground color
    # Bright Foreground Colors (90-97)
    "90": ft.colors.with_opacity(0.7, ft.colors.BLACK),  # Often rendered as gray
    "91": ft.colors.RED_ACCENT,  # Or RED_400 / LIGHT_RED
    "92": ft.colors.LIGHT_GREEN,  # Or GREEN_ACCENT
    "93": ft.colors.YELLOW_ACCENT,  # Or LIGHT_YELLOW
    "94": ft.colors.LIGHT_BLUE,  # Or BLUE_ACCENT
    "95": ft.colors.PINK,  # ANSI bright magenta maps well to Flet's PINK
    "96": ft.colors.CYAN_ACCENT,
    "97": ft.colors.WHITE70,  # Brighter white
}

# Loguru simple tags mapping (add more as needed from your logger.py)
# Using lowercase for matching
LOGURU_TAGS = {
    "red": ft.colors.RED,
    "green": ft.colors.GREEN,
    "yellow": ft.colors.YELLOW,
    "blue": ft.colors.BLUE,
    "magenta": ft.colors.PINK,
    "cyan": ft.colors.CYAN,
    "white": ft.colors.WHITE,
    "light-yellow": ft.colors.YELLOW_ACCENT,  # Or specific yellow shade
    "light-green": ft.colors.LIGHT_GREEN,
    "light-magenta": ft.colors.PINK,  # Or specific magenta shade
    "light-cyan": ft.colors.CYAN_ACCENT,  # Or specific cyan shade
    "light-blue": ft.colors.LIGHT_BLUE,
    "fg #ffd700": "#FFD700",  # Handle specific hex colors like emoji
    "fg #3399ff": "#3399FF",  # Handle specific hex colors like emoji
    "fg #66ccff": "#66CCFF",
    "fg #005ba2": "#005BA2",
    "fg #7cffe6": "#7CFFE6",  # 海马体
    "fg #37ffb4": "#37FFB4",  # LPMM
    "fg #00788a": "#00788A",  # 远程
    "fg #3fc1c9": "#3FC1C9",  # Tools
    # Add other colors used in your logger.py simple formats
}

# Regex to find ANSI codes (basic SGR, true-color fg) OR Loguru tags
# Added specific capture for 38;2;r;g;b
ANSI_COLOR_REGEX = re.compile(
    r"(\x1b\[(?:(?:(?:3[0-7]|9[0-7]|1|3|4|22|23|24);?)+|39|0)m)"  # Group 1: Basic SGR codes (like 31, 1;32, 0, 39)
    r"|"
    r"(\x1b\[38;2;(\d{1,3});(\d{1,3});(\d{1,3})m)"  # Group 2: Truecolor FG ( captures full code, Grp 3: R, Grp 4: G, Grp 5: B )
    # r"|(\x1b\[48;2;...m)" # Placeholder for Truecolor BG if needed later
    r"|"
    r"(<(/?)([^>]+)?>)"  # Group 6: Loguru tags ( Grp 7: slash, Grp 8: content )
)


def parse_log_line_to_spans(line: str) -> list[ft.TextSpan]:
    """
    Parses a log line potentially containing ANSI codes OR Loguru tags
    into a list of Flet TextSpan objects.
    Uses a style stack for basic nesting.
    """
    spans = []
    current_pos = 0
    # Stack holds TextStyle objects. Base style is default.
    style_stack = [ft.TextStyle()]

    for match in ANSI_COLOR_REGEX.finditer(line):
        start, end = match.span()
        basic_ansi_code = match.group(1)
        truecolor_ansi_code = match.group(2)
        tc_r, tc_g, tc_b = match.group(3), match.group(4), match.group(5)
        loguru_full_tag = match.group(6)
        loguru_closing_slash = match.group(7)
        loguru_tag_content = match.group(8)

        current_style = style_stack[-1]

        if start > current_pos:
            spans.append(ft.TextSpan(line[current_pos:start], current_style))

        if basic_ansi_code:
            # --- Handle Basic ANSI ---
            params = basic_ansi_code[2:-1]
            if not params or params == "0":  # Reset code
                style_stack = [ft.TextStyle()]  # Reset stack
            else:
                temp_style_dict = {
                    k: getattr(current_style, k, None) for k in ["color", "weight", "italic", "decoration"]
                }
                codes = params.split(";")
                for code in filter(None, codes):
                    style_attr = ANSI_CODES.get(code)
                    if isinstance(style_attr, str):
                        temp_style_dict["color"] = style_attr
                    elif isinstance(style_attr, ft.FontWeight):
                        temp_style_dict["weight"] = None if code == "22" else style_attr
                    elif isinstance(style_attr, ft.TextStyle):
                        if style_attr.italic is not None:
                            temp_style_dict["italic"] = False if code == "23" else style_attr.italic
                        if style_attr.decoration is not None:
                            temp_style_dict["decoration"] = (
                                ft.TextDecoration.NONE if code == "24" else style_attr.decoration
                            )
                    elif style_attr is None and code == "39":
                        temp_style_dict["color"] = None
                style_stack[-1] = ft.TextStyle(**{k: v for k, v in temp_style_dict.items() if v is not None})

        elif truecolor_ansi_code:
            # --- Handle Truecolor ANSI ---
            try:
                r, g, b = int(tc_r), int(tc_g), int(tc_b)
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                # print(f"--- TrueColor Debug: Parsed RGB ({r},{g},{b}) -> {hex_color} ---")
                # Update color in the current style on stack top
                temp_style_dict = {
                    k: getattr(current_style, k, None) for k in ["color", "weight", "italic", "decoration"]
                }
                temp_style_dict["color"] = hex_color
                style_stack[-1] = ft.TextStyle(**{k: v for k, v in temp_style_dict.items() if v is not None})
            except (ValueError, TypeError) as e:
                print(f"Error parsing truecolor ANSI: {e}, Code: {truecolor_ansi_code}")
                # Keep current style if parsing fails

        elif loguru_full_tag:
            if loguru_closing_slash:
                if len(style_stack) > 1:
                    style_stack.pop()
                # print(f"--- Loguru Debug: Closing Tag processed. Stack size: {len(style_stack)} ---")
            elif loguru_tag_content:  # Opening tag
                tag_lower = loguru_tag_content.lower()
                style_attr = LOGURU_TAGS.get(tag_lower)

                # print(f"--- Loguru Debug: Opening Tag --- ")
                # print(f"  Raw Content : {repr(loguru_tag_content)}")
                # print(f"  Lowercase Key: {repr(tag_lower)}")
                # print(f"  Found Attr  : {repr(style_attr)} --- ")

                temp_style_dict = {
                    k: getattr(current_style, k, None) for k in ["color", "weight", "italic", "decoration"]
                }

                if style_attr:
                    if isinstance(style_attr, str):
                        temp_style_dict["color"] = style_attr
                        # print(f"  Applied Color: {style_attr}")
                    # ... (handle other style types if needed)

                    # Push the new style only if the tag was recognized and resulted in a change
                    # (or check if style_attr is not None)
                    new_style = ft.TextStyle(**{k: v for k, v in temp_style_dict.items() if v is not None})
                    # Avoid pushing identical style
                    if new_style != current_style:
                        style_stack.append(new_style)
                        # print(f"  Pushed Style. Stack size: {len(style_stack)}")
                    # else:
                    # print(f"  Style unchanged, stack not pushed.")
                # else:
                # print(f"  Tag NOT FOUND in LOGURU_TAGS.")
            # else: Invalid tag format?

        current_pos = end

    # Add any remaining text after the last match
    final_style = style_stack[-1]
    if current_pos < len(line):
        spans.append(ft.TextSpan(line[current_pos:], final_style))

    return [span for span in spans if span.text]


if __name__ == "__main__":
    # Example Usage & Testing
    test_lines = [
        "This is normal text.",
        "\\x1b[31mThis is red text.\\x1b[0m And back to normal.",
        "\\x1b[1;32mThis is bold green.\\x1b[0m",
        "Text with <red>red tag</red> inside.",
        "Nested <yellow>yellow <bold>bold</bold> yellow</yellow>.",  # Bold tag not handled yet
        "<light-green>Light green message</light-green>",
        "<fg #FFD700>Emoji color</fg #FFD700>",
        "\\x1b[94mBright Blue ANSI\\x1b[0m",
        "\\x1b[3mItalic ANSI\\x1b[0m",
        # Example from user image (simplified)
        "\\x1b[37m2025-05-03 23:00:44\\x1b[0m | \\x1b[1mINFO\\x1b[0m | \\x1b[96m配置\\x1b[0m | \\x1b[1m成功加载配置文件: ...\\x1b[0m",
        "\\x1b[1mDEBUG\\x1b[0m | \\x1b[94m人物信息\\x1b[0m | \\x1b[1m已加载 81 个用户名\\x1b[0m",
        "<level>TIME</level> | <light-green>模块</light-green> | <light-green>消息</light-green>",  # Loguru format string itself
    ]

    # Simple print test (won't show colors in standard terminal)
    for t_line in test_lines:
        print(f"--- Input: {repr(t_line)} ---")
        parsed_spans = parse_log_line_to_spans(t_line)
        print("Parsed Spans:")
        for s in parsed_spans:
            print(
                f"  Text: {repr(s.text)}, Style: color={s.style.color}, weight={s.style.weight}, italic={s.style.italic}, decoration={s.style.decoration}"
            )
        print("-" * 20)

    # To visually test with Flet, you'd run this in a simple Flet app:
    # import flet as ft
    # def main(page: ft.Page):
    #     page.add(ft.Column([
    #         ft.Text(spans=parse_log_line_to_spans(line)) for line in test_lines
    #     ]))
    # ft.app(target=main)

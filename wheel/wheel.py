import io
import math
import random
import colorsys
import asyncio
import discord
from PIL import Image, ImageDraw, ImageFont
import imageio
from redbot.core import commands
from redbot.core.bot import Red

class Wheel(commands.Cog):
    """Spin a temporary wheel with the given options (nothing is saved)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.font = self._load_font(26)

    def _load_font(self, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for path in paths:
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
        return ImageFont.load_default()

    @commands.command(name="wheel")
    @commands.guild_only()
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def wheel(self, ctx: commands.Context, *options: str):
        """
        Spin a temporary wheel with the given options.

        Examples:
        `[p]wheel Pizza Burgers Tacos`
        `[p]wheel "Red Team" "Blue Team" "Green Team"`
        """
        if len(options) < 2:
            return await ctx.send("❌ You need at least **2** options to spin a wheel.")
        if len(options) > 16:
            return await ctx.send("❌ Maximum **16** options allowed.")

        options = [opt.strip() for opt in options if opt.strip()]
        if len(options) < 2:
            return await ctx.send("❌ You need at least **2** valid options.")

        winner_idx = random.randrange(len(options))
        winner = options[winner_idx]

        async with ctx.typing():
            try:
                gif, spin_seconds = await self._make_wheel_gif(options, winner_idx)
            except Exception as e:
                return await ctx.send(f"❌ Failed to generate wheel: `{e}`")

        file = discord.File(fp=gif, filename="wheel.gif")
        await ctx.send(file=file)

        # Wait for the spin to finish, then announce
        await asyncio.sleep(spin_seconds + 0.4)  # small buffer for upload delay
        await ctx.send(f"🎉 The wheel landed on **{winner}**!")

    def _get_colors(self, n: int) -> list[tuple[int, int, int]]:
        cols = []
        for i in range(n):
            h = (i / n + random.uniform(-0.03, 0.03)) % 1.0
            s = random.uniform(0.32, 0.50)   # muted
            v = random.uniform(0.80, 0.94)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            cols.append((int(r * 255), int(g * 255), int(b * 255)))
        return cols

    async def _make_wheel_gif(
        self,
        options: list[str],
        winner_idx: int,
    ) -> tuple[io.BytesIO, float]:
        # Timing configuration
        SPIN_SECONDS = 3.6
        HOLD_SECONDS = 5.0
        SPIN_FRAMES = 36
        HOLD_FRAMES = 50          # 50 frames ≈ 5 seconds when total duration is correct

        size = 500
        center = size // 2
        radius = center - 14
        sector = 360.0 / len(options)
        colors = self._get_colors(len(options))

        rotations = 4
        mid_deg = (winner_idx + 0.5) * sector
        delta = (270 - mid_deg) % 360
        final_offset = rotations * 360 + delta

        imgs: list[Image.Image] = []

        # Spinning frames
        for frame in range(SPIN_FRAMES):
            t = frame / (SPIN_FRAMES - 1)
            ease = 1 - (1 - t) ** 2.7
            offset = ease * final_offset
            imgs.append(self._draw_frame(options, colors, offset, size, center, radius, sector))

        # Hold frames
        final_frame = self._draw_frame(options, colors, final_offset, size, center, radius, sector)
        for _ in range(HOLD_FRAMES):
            imgs.append(final_frame.copy())

        total_frames = len(imgs)
        total_duration = SPIN_SECONDS + HOLD_SECONDS
        frame_duration = total_duration / total_frames

        bio = io.BytesIO()
        imageio.mimsave(
            bio,
            imgs,
            format="GIF",
            duration=frame_duration,
            loop=0,
        )
        bio.seek(0)
        return bio, SPIN_SECONDS

    def _draw_frame(
        self,
        options: list[str],
        colors: list[tuple[int, int, int]],
        offset: float,
        size: int,
        center: int,
        radius: int,
        sector: float,
    ) -> Image.Image:
        im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(im)

        for idx, (opt, col) in enumerate(zip(options, colors)):
            start = idx * sector + offset
            end = start + sector

            draw.pieslice(
                [12, 12, size - 12, size - 12],
                start,
                end,
                fill=col,
                outline=(40, 40, 40),
                width=3,
            )

            ang = math.radians((start + end) / 2)
            tx = center + math.cos(ang) * (radius * 0.55)
            ty = center + math.sin(ang) * (radius * 0.55)

            label = opt if len(opt) <= 12 else opt[:11] + "…"

            brightness = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
            fg = (20, 20, 20) if brightness > 155 else (255, 255, 255)
            stroke = (255, 255, 255) if brightness > 155 else (10, 10, 10)

            bbox = draw.textbbox((0, 0), label, font=self.font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pad = 5
            text_im = Image.new("RGBA", (tw + pad * 2, th + pad * 2), (0, 0, 0, 0))
            td = ImageDraw.Draw(text_im)

            td.text(
                (pad, pad),
                label,
                font=self.font,
                fill=fg,
                stroke_width=3,
                stroke_fill=stroke,
            )

            rot = text_im.rotate(-math.degrees(ang) + 90, expand=True, resample=Image.BICUBIC)
            im.paste(rot, (int(tx - rot.width / 2), int(ty - rot.height / 2)), rot)

        # Arrow
        arrow = [(center - 18, 3), (center + 18, 3), (center, 30)]
        draw.polygon(arrow, fill=(25, 25, 25), outline=(255, 255, 255))
        draw.line(arrow + [arrow[0]], fill=(255, 255, 255), width=2)

        # Outer ring
        draw.ellipse([5, 5, size - 5, size - 5], outline=(40, 40, 40), width=5)

        return im

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
        try:
            self.font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26
            )
        except OSError:
            self.font = ImageFont.load_default()

    @commands.command(name="wheel")
    @commands.guild_only()
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def wheel(self, ctx: commands.Context, *options: str):
        """
        Spin a temporary wheel with the given options.

        Examples:
        `[p]wheel Pizza Burgers Tacos`
        `[p]wheel "Red Team" "Blue Team" "Green Team"`
        """
        if len(options) < 2:
            return await ctx.send("❌ You need at least **2** options to spin a wheel.")

        if len(options) > 20:
            return await ctx.send("❌ Maximum **20** options allowed.")

        options = [opt.strip() for opt in options if opt.strip()]
        if len(options) < 2:
            return await ctx.send("❌ You need at least **2** valid options.")

        winner_idx = random.randrange(len(options))
        winner = options[winner_idx]

        async with ctx.typing():
            gif, spin_duration = await self._make_wheel_gif(options, winner_idx)

        file = discord.File(fp=gif, filename="wheel.gif")
        await ctx.send(file=file)

        # Wait until the spinning part is over, then announce the winner
        await asyncio.sleep(spin_duration)
        await ctx.send(f"🎉 The wheel landed on **{winner}**!")

    def _get_colors(self, n: int) -> list[tuple[int, int, int]]:
        """Generate muted / less saturated colors."""
        cols = []
        for i in range(n):
            h = (i / n + random.uniform(-0.03, 0.03)) % 1.0
            s = random.uniform(0.35, 0.55)
            v = random.uniform(0.78, 0.95)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            cols.append((int(r * 255), int(g * 255), int(b * 255)))
        return cols

    async def _make_wheel_gif(
        self,
        options: list[str],
        winner_idx: int,
        spin_frames: int = 42,
        hold_frames: int = 70,          # ≈ 5 seconds of hold
        spin_duration: float = 3.8,     # how long the actual spin lasts
        hold_duration: float = 5.0,     # exact 5 second hold
    ) -> tuple[io.BytesIO, float]:
        size = 520
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
        for frame in range(spin_frames):
            t = frame / (spin_frames - 1)
            ease = 1 - (1 - t) ** 2.8
            offset = ease * final_offset
            imgs.append(self._draw_frame(options, colors, offset, size, center, radius, sector))

        # 5-second hold on the final frame
        final_frame = self._draw_frame(options, colors, final_offset, size, center, radius, sector)
        for _ in range(hold_frames):
            imgs.append(final_frame.copy())

        total_duration = spin_duration + hold_duration

        bio = io.BytesIO()
        imageio.mimsave(
            bio,
            imgs,
            format="GIF",
            duration=total_duration / len(imgs),
            loop=0,
        )
        bio.seek(0)
        return bio, spin_duration

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
                [14, 14, size - 14, size - 14],
                start,
                end,
                fill=col,
                outline=(30, 30, 30),
                width=3,
            )

            ang = math.radians((start + end) / 2)
            tx = center + math.cos(ang) * (radius * 0.55)
            ty = center + math.sin(ang) * (radius * 0.55)

            label = opt if len(opt) <= 13 else opt[:12] + "…"

            brightness = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
            fg = (15, 15, 15) if brightness > 150 else (255, 255, 255)
            stroke = (255, 255, 255) if brightness > 150 else (0, 0, 0)

            bbox = draw.textbbox((0, 0), label, font=self.font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            pad = 6
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

        # Top arrow
        arrow = [
            (center - 20, 2),
            (center + 20, 2),
            (center, 32),
        ]
        draw.polygon(arrow, fill=(20, 20, 20), outline=(255, 255, 255))
        draw.polygon(arrow, outline=(255, 255, 255), width=2)

        # Outer ring
        draw.ellipse([6, 6, size - 6, size - 6], outline=(35, 35, 35), width=5)

        return im

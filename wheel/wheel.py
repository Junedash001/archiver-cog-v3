import io
import math
import random
import colorsys
import discord
from PIL import Image, ImageDraw, ImageFont
import imageio
from redbot.core import commands
from redbot.core.bot import Red

class Wheel(commands.Cog):
    """Spin a temporary wheel with the given options (nothing is saved)."""

    def __init__(self, bot: Red):
        self.bot = bot
        # Try a common system font, fall back to default if missing
        try:
            self.font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 20
            )
        except OSError:
            self.font = ImageFont.load_default()

    @commands.command(name="wheel")
    @commands.guild_only()
    @commands.cooldown(1, 8, commands.BucketType.user)  # mild anti-spam
    async def wheel(self, ctx: commands.Context, *options: str):
        """
        Spin a temporary wheel with the given options.

        Examples:
        `[p]wheel Pizza Burgers Tacos`
        `[p]wheel "Red Team" "Blue Team" "Green Team"`
        `[p]wheel A B C D E`
        """
        if len(options) < 2:
            return await ctx.send("❌ You need at least **2** options to spin a wheel.")

        if len(options) > 20:
            return await ctx.send("❌ Maximum **20** options allowed.")

        # Clean empty options just in case
        options = [opt.strip() for opt in options if opt.strip()]
        if len(options) < 2:
            return await ctx.send("❌ You need at least **2** valid options.")

        winner_idx = random.randrange(len(options))
        winner = options[winner_idx]

        async with ctx.typing():
            gif = await self._make_wheel_gif(options, winner_idx)

        file = discord.File(fp=gif, filename="wheel.gif")
        await ctx.send(f"🎉 The wheel stops on **{winner}**!", file=file)

    def _get_colors(self, n: int) -> list[tuple[int, int, int]]:
        """Generate n bright, distinct RGB colors."""
        cols = []
        for i in range(n):
            h = (i / n + random.uniform(-0.05, 0.05)) % 1.0
            s = random.uniform(0.65, 0.95)
            v = random.uniform(0.75, 1.0)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            cols.append((int(r * 255), int(g * 255), int(b * 255)))
        return cols

    async def _make_wheel_gif(
        self,
        options: list[str],
        winner_idx: int,
        frames: int = 36,
        duration: float = 3.2,
    ) -> io.BytesIO:
        size = 500
        center = size // 2
        radius = center - 12
        sector = 360.0 / len(options)
        colors = self._get_colors(len(options))

        # Calculate final rotation so the winner lands under the top arrow
        rotations = 4
        mid_deg = (winner_idx + 0.5) * sector
        delta = (270 - mid_deg) % 360
        final_offset = rotations * 360 + delta

        imgs: list[Image.Image] = []

        for frame in range(frames):
            t = frame / (frames - 1)
            # Ease-out so it slows down naturally
            ease = 1 - (1 - t) ** 2.5
            offset = ease * final_offset

            im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(im)

            for idx, (opt, col) in enumerate(zip(options, colors)):
                start = idx * sector + offset
                end = start + sector

                # Draw the slice
                draw.pieslice(
                    [12, 12, size - 12, size - 12],
                    start,
                    end,
                    fill=col,
                    outline=(30, 30, 30),
                    width=2,
                )

                # Label
                ang = math.radians((start + end) / 2)
                tx = center + math.cos(ang) * (radius * 0.58)
                ty = center + math.sin(ang) * (radius * 0.58)

                label = opt if len(opt) <= 14 else opt[:13] + "…"
                brightness = 0.299 * col[0] + 0.587 * col[1] + 0.114 * col[2]
                fg = "black" if brightness > 140 else "white"
                stroke = "white" if fg == "black" else "black"

                # Create text image so we can rotate it
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
                    stroke_width=2,
                    stroke_fill=stroke,
                )

                # Rotate text so it follows the slice angle
                rot = text_im.rotate(-math.degrees(ang) + 90, expand=True, resample=Image.BICUBIC)
                im.paste(
                    rot,
                    (int(tx - rot.width / 2), int(ty - rot.height / 2)),
                    rot,
                )

            # Fixed arrow at the top (12 o'clock)
            arrow = [
                (center - 18, 4),
                (center + 18, 4),
                (center, 28),
            ]
            draw.polygon(arrow, fill=(20, 20, 20), outline=(255, 255, 255))

            # Outer ring
            draw.ellipse([8, 8, size - 8, size - 8], outline=(40, 40, 40), width=4)

            imgs.append(im)

        bio = io.BytesIO()
        imageio.mimsave(
            bio,
            imgs,
            format="GIF",
            duration=duration / frames,
            loop=0,
        )
        bio.seek(0)
        return bio

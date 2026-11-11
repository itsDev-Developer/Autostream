from .base import Ctx, Game  # noqa: F401
from .blocks import Blocks
from .fight import Fight
from .flappy import Flappy
from .racing import Racing

REGISTRY = {"flappy": Flappy, "racing": Racing, "blocks": Blocks, "fight": Fight}

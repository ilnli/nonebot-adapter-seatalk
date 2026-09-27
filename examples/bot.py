import nonebot
from nonebot.adapters.seatalk import Adapter

nonebot.init()
nonebot.get_driver().register_adapter(Adapter)
nonebot.load_plugins("examples/plugins")

if __name__ == "__main__":
    nonebot.run()

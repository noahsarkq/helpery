# Taken from megadlbot_oss <https://github.com/eyaadh/megadlbot_oss/blob/master/mega/webserver/routes.py>
# Thanks to Eyaadh <https://github.com/eyaadh>

import re
from threading import local
import time
import math
import logging
import secrets
import mimetypes
import aiohttp
from aiohttp import web
from WebStreamer.vars import Var
from aiohttp.http_exceptions import BadStatusLine
from WebStreamer.utils.file_id import get_unique_id
from WebStreamer.bot import multi_clients, work_loads
from WebStreamer import StartTime, __version__, bot_info
from WebStreamer.utils.time_format import get_readable_time
# from WebStreamer.bot.clients import multi_clients, work_loads
from WebStreamer.utils.custom_dl import TGCustomYield, chunk_size, offset_fix

routes = web.RouteTableDef()


@routes.get("/status", allow_head=True)
async def root_route_handler(request):
    logging.info(f"status >> {str(work_loads)}")
    return web.json_response({
        "server_status":
        "running",
        "uptime":
        get_readable_time(time.time() - StartTime),
        "telegram_bot":
        "@" + bot_info.username,
        "connected_bots":
        len(multi_clients),
        "loads":
        str(work_loads),
        "version":
        __version__,
    })


@routes.get(r"/{pathx:\d+}/{hsh:\w+}", allow_head=True)
async def stream_handler(request):
    _index = min(work_loads, key=work_loads.get)
    faster_client = multi_clients[_index]
    work_loads[_index] += 1
    if Var.MULTI_CLIENT:
        logging.info(f"Client {_index} is now serving {request.remote}")
#         logging.info(f"after >> {str(work_loads)}")
    # logging.info(f"before >> {str(work_loads)}")

    try:
        # logging.info(request)
        requestx = re.findall(r"/(\d+)/(\w+)", str(request))[0]
        message_id = int(requestx[0])
        local_hash = requestx[1]
        # logging.info(local_hash)
        # logging.info(message_id)
        if local_hash in Var.HASH:
            logging.info(message_id)
            return await media_streamer(request, message_id, faster_client,
                                        work_loads, _index)
        else:
            return web.json_response("Are you sure you have Access")

    except Exception as e:
        logging.info(e)
        pass
    finally:
        work_loads[_index] -= 1


async def media_streamer(request: web.Request, message_id: int, faster_client,
                         work_loads, index):
    range_header = request.headers.get("Range", 0)
    #logging.info(request.headers)
#     logging.info(f"{str(work_loads)}")

    tg_connect = TGCustomYield(faster_client)
    media_msg = await faster_client.get_messages(Var.BIN_CHANNEL, message_id)

    file_properties = await tg_connect.generate_file_properties(media_msg)
    file_size = file_properties.file_size

    if range_header:
        from_bytes, until_bytes = range_header.replace("bytes=", "").split("-")
        # logging.info(from_bytes)
        # logging.info(until_bytes)
        from_bytes = int(from_bytes)
        until_bytes = int(until_bytes) if until_bytes else file_size - 1
    else:
        from_bytes = request.http_range.start or 0
        # logging.info(from_bytes)
        until_bytes = request.http_range.stop or file_size - 1
        # logging.info(until_bytes)

    req_length = until_bytes - from_bytes
    new_chunk_size = await chunk_size(req_length)
    offset = await offset_fix(from_bytes, new_chunk_size)
    first_part_cut = from_bytes - offset
    last_part_cut = (until_bytes % new_chunk_size) + 1
    part_count = math.ceil(req_length / new_chunk_size)
    body = tg_connect.yield_file(media_msg, offset, first_part_cut,
                                 last_part_cut, part_count, new_chunk_size)

    mime_type = file_properties.mime_type
    file_name = file_properties.file_name
    disposition = "attachment"
    if mime_type:
        if not file_name:
            try:
                file_name = f"{secrets.token_hex(2)}.{mime_type.split('/')[1]}"
            except (IndexError, AttributeError):
                file_name = f"{secrets.token_hex(2)}.unknown"
    else:
        if file_name:
            mime_type = mimetypes.guess_type(file_properties.file_name)
        else:
            mime_type = "application/octet-stream"
            file_name = f"{secrets.token_hex(2)}.unknown"
    if "video/" in mime_type or "audio/" in mime_type:
        disposition = "inline"
    try:
        return_resp = web.Response(
            status=206 if range_header else 200,
            body=body,
            headers={
                "Content-Type": mime_type,
                # "Connection": "close",
                # " Keep-Alive": "timeout=5, max=1000",
                "Content-Length": str(file_size),
                "Range": f"bytes={from_bytes}-{until_bytes}",
                "Content-Range":
                f"bytes {from_bytes}-{until_bytes}/{file_size}",
                "Content-Disposition":
                f'{disposition}; filename="{file_name}"',
                "Accept-Ranges": "bytes",
            },
        )

        if return_resp.status == 200:
            logging.info("200 Happened")
            return_resp.headers.add("Content-Length", str(file_size))
        if return_resp.status == 503:
            logging.info("503 Happened")

        if return_resp.status == 499:
            logging.info("499 Happened")

        #logging.info(return_resp.status)
    # logging.info(web.WebSocketResponse())
    #logging.info(f"last >> {work_loads}")
    except Exception as e:
        logging.info(e)

        pass
    #logging.info(return_resp)
    return return_resp

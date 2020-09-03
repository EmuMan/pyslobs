"""An object-based API wrapper for the Streamlabs OBS (SLOBS) API"""

import json
import time
from pprint import pprint
import asyncio
import win32file, win32pipe
import pywintypes
from typing import NoReturn, Union
from collections import deque
from string import ascii_uppercase


class RequestFailed(Exception):
    def __init__(self, message):
        self.message = message

def to_lowercase_with_underscores(s):
    return "".join((c if c not in ascii_uppercase else ("_" + c.lower())) for c in s)

class Promise:

    def __init__(self, slobs, data):
        self.slobs = slobs
        self.resource_id = data["result"]["resourceId"]
        self.rejected = None
        self.response = None

    async def get(self) -> Union[dict, None]:
        # maybe rename?
        # basically wait for the promise to be fulfilled
        while True:
            for i, response in enumerate(self.slobs.incoming_queue["fulfilled_promise"]):
                if response["result"]["resourceId"] == self.resource_id:
                    self.rejected = response["result"]["isRejected"]
                    self.response = self.slobs.incoming_queue["fulfilled_promise"].pop(i) if "data" in response["result"] else None
                    return self.response
            await asyncio.sleep(0.1)

    async def check_rejected(self) -> bool:
        if self.rejected == None:
            await self.get()
        return self.rejected


class SlobsConnection:
    
    def __init__(self):
        self.pipe_handle = None
        try:
            self.pipe_handle = win32file.CreateFile(
                r'\\.\pipe\slobs',
                win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                0,
                None,
                win32file.OPEN_EXISTING,
                0,
                None
            )
        except pywintypes.error:
            print("Error: Streamlabs OBS must be open for this script to work.")
            exit(1)

        self.outgoing_queue = deque()
        self.incoming_queue = {"helper": [], "subscription": [], "event": [], "promise": [], "fulfilled_promise": []}
        self.current_id = 1
        self.running = True

    def __del__(self):
        win32file.CloseHandle(self.pipe_handle)
    
    async def recieve_if_available(self) -> None:
        raw = b""
        # Only recieve data if there is data available in the pipe
        while win32pipe.PeekNamedPipe(self.pipe_handle, 0)[1] != 0:
            raw += win32file.ReadFile(self.pipe_handle, 1024)[1]
        if raw == b"": return
        # Split the raw bytes into seperate messages if possible, add to queue
        for response in [r for r in raw.split(b"\n") if r != b""]:
            json_data = json.loads(str(response, "ascii"))
            result = json_data["result"]
            if isinstance(result, dict):
                # promises and subscriptions are basically two different things using the same format, separate them here
                if result["_type"] == "HELPER":
                    # idk if this even happens ever
                    self.incoming_queue["helper"].append(json_data)
                elif result["_type"] == "SUBSCRIPTION":
                    if result["emitter"] == "STREAM":
                        self.incoming_queue["subscription"].append(json_data)
                    if result["emitter"] == "PROMISE":
                        self.incoming_queue["promise"].append(json_data)
                elif result["_type"] == "EVENT":
                    if result["emitter"] == "STREAM":
                        self.incoming_queue["event"].append(json_data)
                    if result["emitter"] == "PROMISE":
                        self.incoming_queue["fulfilled_promise"].append(json_data)
            else:
                # the result is probably supposed to be a helper
                self.incoming_queue["helper"].append(json_data)
    
    async def send_request(self, method: str, resource: str, args: list=None) -> int:
        request_id = self.current_id
        self.current_id += 1
        to_send = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": {"resource": resource}}
        if args:
            to_send["params"]["args"] = args
        self.outgoing_queue.append(bytes(json.dumps(to_send, ensure_ascii=True), "ascii"))
        return request_id

    async def wait_for_response(self, request_id: int) -> dict:
        while True:
            for i, response in enumerate(self.incoming_queue["helper"]):
                if response["id"] == request_id:
                    return self.incoming_queue["helper"].pop(i)
            await asyncio.sleep(0.1)

    async def send_and_wait_response(self, method: str, resource: str, args: list=None) -> dict:
        r_id = await self.send_request(method, resource, args)
        return await self.wait_for_response(r_id)

    async def wait_for_promise(self, request_id: int) -> Promise:
        while True:
            for i, response in enumerate(self.incoming_queue["promise"]):
                if response["id"] == request_id:
                    return Promise(self, self.incoming_queue["promise"].pop(i))
            await asyncio.sleep(0.1)

    async def send_and_wait_promise(self, method: str, resource: str, args: list=None) -> Promise:
        r_id = await self.send_request(method, resource, args)
        return await self.wait_for_promise(r_id)

    async def close(self) -> None:
        self.running = False

    async def main_loop(self) -> NoReturn:
        while self.running:
            await self.recieve_if_available()
            # Send all messages in outgoing queue
            while not len(self.outgoing_queue) == 0:
                win32file.WriteFile(self.pipe_handle, self.outgoing_queue.popleft())
            await asyncio.sleep(0.1)


class Slobs:

    def __init__(self):
        self.connection = SlobsConnection()
        self.subscriptions = {}
        self.on_ready_func = None

    async def create_scene(self, name: str):
        response = await self.connection.send_and_wait_response("createScene", "ScenesService")
        return Scene(self.connection, response["result"])
    
    async def get_scenes(self, key=None) -> list:
        response = await self.connection.send_and_wait_response("getScenes", "ScenesService")
        scenes = [Scene(self.connection, d) for d in response["result"]]
        if key:
            return [s for s in scenes if key(s)]
        else:
            return scenes

    async def get_scene(self, key=None):
        # probably could have just taken the first element from a get_scenes search with
        # minimal performance impact but oh well
        response = await self.connection.send_and_wait_response("getScenes", "ScenesService")
        if key:
            for d in response["result"]:
                if key(obj := Scene(self.connection, d)):
                    return obj
            return None
        else:
            return Scene(self.connection, response[0])

    async def get_active_scene(self):
        response = await self.connection.send_and_wait_response("activeScene", "ScenesService")
        return Scene(self.connection, response["result"])

    async def create_scene_collection(self, name: str):
        promise = await self.connection.send_and_wait_promise("create", "SceneCollectionsService", [{"name": name}])
        if not promise.check_rejected():
            return SceneCollection(self.connection, promise.response)
        else:
            raise RequestFailed("could not create new scene collection")

    async def get_scene_collections(self) -> list:
        response = await self.connection.send_and_wait_response("collections", "SceneCollectionsService")
        return [SceneCollection(self.connection, d) for d in response["result"]]

    async def get_audio_sources(self, key=None) -> list:
        response = await self.connection.send_and_wait_response("getSources", "AudioService")
        sources = [AudioSource(self.connection, d) for d in response["result"]]
        if key:
            return [s for s in sources if key(s)]
        else:
            return sources

    async def get_audio_source(self, key=None):
        # see Slobs.get_scene
        response = await self.connection.send_and_wait_response("getSources", "AudioService")
        if key:
            for d in response["result"]:
                if key(obj := AudioSource(self.connection, d)):
                    return obj
            return None
        else:
            return AudioSource(self.connection, response[0])

    async def get_performance_state(self) -> dict:
        # TODO: Make more clean? efficient?
        response = await self.connection.send_and_wait_response("getModel", "PerformanceService")
        response["result"]["cpu"] = response["result"].pop("CPU")
        return {to_lowercase_with_underscores(k):v for k, v in response["result"].items()}

    async def get_source_types(self) -> list:
        response = await self.connection.send_and_wait_response("getAvailableSourcesTypesList", "SourcesService")
        return response["result"]

    async def create_source(self, name: str, source_type: str, channel: int=None, is_temporary=False):
        options = {"isTemporary": is_temporary}
        if channel != None:
            options["channel"] = channel
        # TODO: figure out what the settings parameter actually does
        response = await self.connection.send_and_wait_response("createSource", "SourcesService", [{}, options])
        return Source(self.connection, response["result"])

    async def create_source_from_file(self, file_path: str):
        response = await self.connection.send_and_wait_response("addFile", "SourcesService", [file_path])
        return Source(self.connection, response["result"])

    async def get_sources(self) -> list:
        response = await self.connection.send_and_wait_response("getSources", "SourcesService")
        return [Source(self.connection, d) for d in response["result"]]

    async def get_sources_by_name(self, name: str) -> list:
        response = await self.connection.send_and_wait_response("getSourcesByName", "SourcesService", [name])
        return [Source(self.connection, d) for d in response["result"]]
    
    async def show_add_source(self, source_type: str=None) -> None:
        if source_type:
            await self.connection.send_and_wait_response("showAddSource", "SourcesService", [source_type])
        else:
            await self.connection.send_and_wait_response("showShowcase", "SourcesService")

    async def save_replay(self) -> None:
        await self.connection.send_and_wait_response("saveReplay", "StreamingService")

    async def start_replay_buffer(self) -> None:
        await self.connection.send_and_wait_response("startReplayBuffer", "StreamingService")
    
    async def stop_replay_buffer(self) -> None:
        await self.connection.send_and_wait_response("stopReplayBuffer", "StreamingService")

    async def toggle_recording(self) -> None:
        await self.connection.send_and_wait_response("toggleRecording", "StreamingService")
        
    async def toggle_streaming(self) -> None:
        await self.connection.send_and_wait_response("toggleStreaming", "StreamingService")

    async def disable_studio_mode(self) -> None:
        await self.connection.send_and_wait_response("disableStudioMode", "TransitionsService")

    async def enable_studio_mode(self) -> None:
        await self.connection.send_and_wait_response("enableStudioMode", "TransitionsService")
        
    async def execute_studio_mode_transition(self) -> None:
        await self.connection.send_and_wait_response("executeStudioModeTransition", "TransitionsService")

    # TODO: Decorator to create a subscription
    def subscription(self, f):
        self.subscriptions[f.__name__] = f
        return f

    def on_tick(self, f):
        self.connection.on_tick_func = f
        return f
    
    def on_ready(self, f):
        self.on_ready_func = f
        return f

    def run(self):
        loop = asyncio.get_event_loop()
        loop.create_task(self.connection.main_loop())
        if self.on_ready_func != None:
            loop.create_task(self.on_ready_func())
        loop.run_forever()


class SceneCollection:

    def __init__(self, connection, data):
        self.connection = connection
        self.id = data["id"]
        self.name = data["name"]
        self.modified = data["modified"]
        self.auto = data["auto"]
        self.operating_system = data["operatingSystem"]
        self.deleted = data["deleted"]
        self.needs_rename = data["needsRename"]
        try:
            self.server_id = data["serverId"]
            print("it worked i guess")
        except KeyError:
            print("it did not work")

    async def delete(self) -> None:
        r_id = await self.connection.send_request("delete", "SceneCollectionsService", args=[self.id])
        await self.connection.wait_for_promise(r_id)
    
    async def set_active(self) -> None:
        r_id = await self.connection.send_request("load", "SceneCollectionsService", args=[self.id])
        await self.connection.wait_for_promise(r_id)

    async def rename(self, new_name: str) -> bool:
        r_id = await self.connection.send_request("rename", "SceneCollectionsService", args=[self.id])
        promise = await self.connection.wait_for_promise(r_id)
        # only change the name if the name change went through
        # also return the success
        if not await promise.check_rejected():
            self.name = new_name
            return True
        return False


class Scene:

    def __init__(self, connection, data):
        self.connection = connection
        self.resource_id = data["resourceId"]
        self.id = data["id"]
        self.name = data["name"]
        # self.nodes = [Node(connection, d) for d in data["nodes"]] # probably gonna remove

    async def set_active(self) -> bool:
        response = await self.connection.send_and_wait_response("makeSceneActive", "ScenesService", [self.id])
        return response["result"]
    
    async def delete(self) -> None:
        await self.connection.send_and_wait_response("removeScene", "ScenesService", [self.id])

    async def get_audio_sources(self):
        await self.connection.send_and_wait_response("getSourcesForScene", "AudioService", [self.id])

    async def get_audio_source(self, name: str):
        # see Slobs.get_scene
        sources = await self.get_audio_sources()
        return next((s for s in sources if s.name == name), None)


class Source:

    def __init__(self, connection: SlobsConnection, data: dict):
        self.connection = connection
        self.resource_id = data["resourceId"]
        self.source_id = data["sourceId"]
        self.id = data["id"]
        self.name = data["name"]
        self.type = data["type"]
        self.audio = data["audio"]
        self.video = data["video"]
        self._async = data["async"]
        self.muted = data["muted"]
        self.width = data["width"]
        self.height = data["height"]
        self.do_not_duplicate = data["doNotDuplicate"]

    async def delete(self) -> None:
        await self.connection.send_and_wait_response("removeSource", "SourcesService", [self.id])

    async def duplicate(self) -> None:
        await self.connection.send_and_wait_response("duplicate", self.resource_id)

    async def get_model(self) -> None:
        # TODO: Implement
        pass

    async def get_properties_form_data(self) -> None:
        # TODO: Implement
        pass

    async def get_settings(self) -> dict:
        return (await self.connection.send_and_wait_response("getSettings", self.resource_id))["result"]

    async def has_props(self) -> bool:
        return (await self.connection.send_and_wait_response("hasProps", self.resource_id))["result"]

    async def refresh(self) -> None:
        await self.connection.send_and_wait_response("refresh", self.resource_id)

    async def set_name(self, name: str) -> None:
        await self.connection.send_and_wait_response("setName", self.resource_id, [name])

    async def set_properties_form_data(self) -> None:
        # TODO: Implement
        pass

    async def update_settings(self, settings: dict) -> None:
        await self.connection.send_and_wait_response("updateSettings", self.resource_id, [settings])

    async def show_properties(self) -> None:
        await self.connection.send_and_wait_response("showSourceProperties", "SourcesService", [self.source_id])

    


class AudioSource:

    def __init__(self, connection: SlobsConnection, data: dict):
        self.connection = connection
        self.resource_id = data["resourceId"]
        self.name = data["name"]
        self.source_id = data["sourceId"]
        self.fader = data["fader"]
        self.audio_mixers = data["audioMixers"]
        self.monitoring_type = data["monitoringType"]
        self.force_mono = data["forceMono"]
        self.sync_offset = data["syncOffset"]
        self.muted = data["muted"]
        self.mixer_hidden = data["mixerHidden"]

    async def set_deflection(self, deflection: int) -> None:
        await self.connection.send_and_wait_response("setDeflection", self.resource_id, [deflection])
        self.fader["deflection"] = deflection
    
    async def set_muted(self, muted: bool) -> None:
        await self.connection.send_and_wait_response("setMuted", self.resource_id, [muted])
        self.muted = muted

class SceneItem:

    def __init__(self, connection: SlobsConnection, data: dict):
        self.connection = connection
        self.id = data["id"]
        self.locked = data["locked"]
        self.name = data["name"]
        self.node_id = data["nodeId"]
        self.parent_id = data["parentId"]
        self.recording_visible = data["recordingVisible"]
        self.scene_id = data["sceneId"]
        self.scene_item_id = data["sceneItemId"]
        self.scene_node_type = data["sceneNodeType"]
        self.source_id = data["sourceId"]
        self.stream_visible = data["streamVisible"]
        self.transform = data["transform"]
        self.visible = data["visible"]
    
    async def add_to_selection(self) -> None:
        await self.connectionsend_and_wait_response
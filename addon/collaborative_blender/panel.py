"""Sidebar panel in the 3D viewport showing room and connection status."""

import bpy


class COLLAB_PT_main(bpy.types.Panel):
    bl_label = "Collaborative"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Collaborative"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Status: not connected")
        layout.operator("collaborative.join_room")
        layout.operator("collaborative.leave_room")


def register() -> None:
    bpy.utils.register_class(COLLAB_PT_main)


def unregister() -> None:
    bpy.utils.unregister_class(COLLAB_PT_main)

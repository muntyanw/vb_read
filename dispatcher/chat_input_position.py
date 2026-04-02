def resolve_chat_input_xy(s) -> tuple[int, int]:
    input_x = int(s.search_board_mess_x_start) + 240
    input_y = int(s.search_board_mess_y_end) + 28
    return input_x, input_y

package net.carlevato.leapsquick;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public class PillReminderBootReceiver extends BroadcastReceiver {
  public void onReceive(Context context, Intent intent){ PillReminderReceiver.scheduleAll(context); }
}

package net.carlevato.leapsquick;

import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import java.text.SimpleDateFormat;
import java.util.Calendar;
import java.util.Locale;

public class PillReminderReceiver extends BroadcastReceiver {
  static final String MORNING_ACTION="net.carlevato.leapsquick.MORNING_REMINDER";
  static final String NIGHT_ACTION="net.carlevato.leapsquick.NIGHT_REMINDER";
  private static final String CHANNEL="pill_reminders";
  private static final int MORNING_ID=830;
  private static final int NIGHT_ID=2230;

  public void onReceive(Context context, Intent intent){
    String action=intent.getAction();
    String kind=MORNING_ACTION.equals(action)?"supplements_morning":"supplements_evening";
    if(!takenToday(context,kind)) showReminder(context,kind);
    schedule(context, action, MORNING_ACTION.equals(action)?8:22, MORNING_ACTION.equals(action)?30:30, MORNING_ACTION.equals(action)?MORNING_ID:NIGHT_ID);
  }

  static void scheduleAll(Context context){
    schedule(context,MORNING_ACTION,8,30,MORNING_ID);
    schedule(context,NIGHT_ACTION,22,30,NIGHT_ID);
  }

  private static void schedule(Context context,String action,int hour,int minute,int requestCode){
    Calendar next=Calendar.getInstance();
    next.set(Calendar.HOUR_OF_DAY,hour); next.set(Calendar.MINUTE,minute); next.set(Calendar.SECOND,0); next.set(Calendar.MILLISECOND,0);
    if(next.getTimeInMillis()<=System.currentTimeMillis()) next.add(Calendar.DATE,1);
    Intent intent=new Intent(context,PillReminderReceiver.class).setAction(action);
    PendingIntent pending=PendingIntent.getBroadcast(context,requestCode,intent,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
    AlarmManager alarms=(AlarmManager)context.getSystemService(Context.ALARM_SERVICE);
    if(Build.VERSION.SDK_INT>=31 && alarms.canScheduleExactAlarms()) alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,next.getTimeInMillis(),pending);
    else alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP,next.getTimeInMillis(),pending);
  }

  static void markTaken(Context context,String kind){
    context.getSharedPreferences("leaps",0).edit().putString(kind+"_taken_on",today()).apply();
    ((NotificationManager)context.getSystemService(Context.NOTIFICATION_SERVICE)).cancel("pill", "supplements_morning".equals(kind)?MORNING_ID:NIGHT_ID);
  }

  private static boolean takenToday(Context context,String kind){
    return today().equals(context.getSharedPreferences("leaps",0).getString(kind+"_taken_on",""));
  }

  private static String today(){ return new SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Calendar.getInstance().getTime()); }

  private static void showReminder(Context context,String kind){
    boolean morning="supplements_morning".equals(kind);
    NotificationManager notifications=(NotificationManager)context.getSystemService(Context.NOTIFICATION_SERVICE);
    Uri sound=RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM);
    if(sound==null) sound=RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
    AudioAttributes audio=new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ALARM).build();
    NotificationChannel channel=new NotificationChannel(CHANNEL,"Pill reminders",NotificationManager.IMPORTANCE_HIGH);
    channel.setDescription("Persistent reminders for morning and night pills"); channel.enableVibration(true); channel.setSound(sound,audio);
    notifications.createNotificationChannel(channel);
    Intent open=new Intent(context,MainActivity.class);
    PendingIntent openPending=PendingIntent.getActivity(context,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
    Notification notification=new Notification.Builder(context,CHANNEL)
      .setSmallIcon(R.drawable.ic_pill).setContentTitle(morning?"Morning pills due":"Night pills due")
      .setContentText(morning?"Take your D3, Omega-3, and Creatine, then tap Morning Pills in the widget.":"Take Magnesium and Probiotic, then tap Night Pills in the widget.")
      .setContentIntent(openPending).setCategory(Notification.CATEGORY_ALARM).setPriority(Notification.PRIORITY_HIGH)
      .setOngoing(true).setAutoCancel(false).build();
    notifications.notify("pill",morning?MORNING_ID:NIGHT_ID,notification);
  }
}
